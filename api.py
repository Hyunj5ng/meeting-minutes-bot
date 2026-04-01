from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Body
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from enum import Enum
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
import aiofiles
from datetime import datetime
from stt_module import STTProcessor
from gpt_summarizer import GPTSummarizer
from email_service import send_summary_email
from rag_service import RAGService
import uuid
import time
import boto3

# 데이터베이스 관련 임포트
from database import get_db, engine, Base
from models import TranscriptRecord, SummaryRecord, User
from auth import get_current_user, verify_google_token, create_access_token, create_refresh_token, verify_refresh_token, revoke_refresh_token
import crud


# ============================================
# Pydantic 모델
# ============================================

class SummaryUpdateRequest(BaseModel):
    summary: str


# API 모델별 가격표 (USD per 1M tokens, Whisper는 USD per minute)
MODEL_PRICING = {
    "whisper-large-v3-turbo": {"per_minute": 0.000667},
    # OpenAI
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    # Anthropic
    "claude-opus-4.6": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    # DeepSeek
    "deepseek-r1": {"input": 0.70, "output": 2.50},
    "deepseek-chat": {"input": 0.32, "output": 0.89},
    "deepseek-v3.2": {"input": 0.26, "output": 0.38},
    # Meta Llama
    "llama-3.3-70b": {"input": 2.75, "output": 2.75},
    "llama-4-maverick": {"input": 0.15, "output": 0.60},
    "llama-4-scout": {"input": 0.08, "output": 0.30},
}

# 사용량 제한 (환경변수로 설정 가능) — STT 분(minutes) 단위만 적용
DAILY_STT_LIMIT_MINUTES = int(os.getenv("DAILY_STT_LIMIT_MINUTES", "120"))
MONTHLY_STT_LIMIT_MINUTES = int(os.getenv("MONTHLY_STT_LIMIT_MINUTES", "600"))


def calculate_stt_cost(audio_duration_seconds: float) -> float:
    """STT 비용 계산 (USD). Groq Whisper는 분당 $0.000667"""
    if not audio_duration_seconds or audio_duration_seconds <= 0:
        return 0.0
    minutes = audio_duration_seconds / 60.0
    return round(minutes * MODEL_PRICING["whisper-large-v3-turbo"]["per_minute"], 6)


def calculate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """LLM 비용 계산 (USD). 토큰 수 × 모델별 단가"""
    pricing = MODEL_PRICING.get(model)
    if not pricing or "input" not in pricing:
        return 0.0
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 6)


def check_usage_limit(db: Session, user_id: int, audio_minutes: float = 0.0):
    """STT 사용량(분) 한도를 확인하고 초과 시 HTTPException(429)을 발생시킨다."""
    daily_used = crud.get_usage_minutes(db, user_id, "stt", period="daily")
    if daily_used + audio_minutes > DAILY_STT_LIMIT_MINUTES:
        remaining = max(0, DAILY_STT_LIMIT_MINUTES - daily_used)
        raise HTTPException(
            status_code=429,
            detail=f"일일 사용 한도({DAILY_STT_LIMIT_MINUTES}분)를 초과합니다. 잔여: {remaining:.0f}분. 내일 다시 시도해주세요."
        )

    monthly_used = crud.get_usage_minutes(db, user_id, "stt", period="monthly")
    if monthly_used + audio_minutes > MONTHLY_STT_LIMIT_MINUTES:
        remaining = max(0, MONTHLY_STT_LIMIT_MINUTES - monthly_used)
        raise HTTPException(
            status_code=429,
            detail=f"월간 사용 한도({MONTHLY_STT_LIMIT_MINUTES}분)를 초과합니다. 잔여: {remaining:.0f}분."
        )


# LLM 모델 선택을 위한 Enum (GPT + Claude)
class LLMModel(str, Enum):
    # OpenAI
    GPT_54_PRO = "gpt-5.4-pro"
    GPT_54 = "gpt-5.4"
    GPT_54_NANO = "gpt-5.4-nano"
    # Anthropic
    CLAUDE_OPUS_46 = "claude-opus-4.6"
    CLAUDE_SONNET_46 = "claude-sonnet-4.6"
    CLAUDE_HAIKU_45 = "claude-haiku-4.5"
    # Google
    GEMINI_25_PRO = "gemini-2.5-pro"
    GEMINI_25_FLASH = "gemini-2.5-flash"
    GEMINI_25_FLASH_LITE = "gemini-2.5-flash-lite"
    # DeepSeek
    DEEPSEEK_R1 = "deepseek-r1"
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_V32 = "deepseek-v3.2"
    # Meta Llama
    LLAMA_33_70B = "llama-3.3-70b"
    LLAMA_4_MAVERICK = "llama-4-maverick"
    LLAMA_4_SCOUT = "llama-4-scout"

# 하위 호환성을 위한 별칭
GPTModel = LLMModel


# Whisper 모델 선택을 위한 Enum
class WhisperModel(str, Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

# 전역 변수로 모델 저장
stt_processor = None
gpt_summarizer = None
rag_service = None

# 업로드 및 출력 디렉토리
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
s3_client = None

if S3_BUCKET:
    s3_client = boto3.client(
        "s3",
        region_name=S3_REGION,
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )


def upload_file_to_s3(local_path: str, key: str, content_type: str = "text/plain"):
    """저장된 파일을 S3(또는 호환 스토리지)로 업로드."""
    if not s3_client or not S3_BUCKET:
        return None
    try:
        s3_client.upload_file(
            local_path,
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        if S3_ENDPOINT_URL:
            base = S3_ENDPOINT_URL.rstrip("/")
            return f"{base}/{S3_BUCKET}/{key}"
        if S3_REGION:
            return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
        return f"s3://{S3_BUCKET}/{key}"
    except Exception as e:
        print(f"S3 업로드 실패 ({local_path}): {e}")
        return None


async def _backfill_embeddings():
    """서버 시작 시 미임베딩 요약을 백그라운드로 백필"""
    try:
        if not rag_service or not rag_service.openai_client:
            print("RAG 백필 스킵: OpenAI 클라이언트 미설정")
            return

        db = next(get_db())
        try:
            records = db.query(SummaryRecord).join(TranscriptRecord).filter(
                TranscriptRecord.user_id.isnot(None)
            ).all()

            if not records:
                return

            print(f"RAG 백필 시작: {len(records)}개 요약")
            for i, record in enumerate(records, 1):
                user_id = record.transcript.user_id
                collection = rag_service._get_collection(user_id)
                doc_id = f"summary_{record.id}"
                # 이미 임베딩된 건 스킵
                existing = collection.get(ids=[doc_id])
                if existing and existing["ids"]:
                    continue

                metadata = {"summary_id": record.id, "user_id": user_id}
                if record.transcript.meeting_title:
                    metadata["meeting_title"] = record.transcript.meeting_title
                if record.transcript.project_name:
                    metadata["project_name"] = record.transcript.project_name

                await rag_service.embed_and_store(
                    user_id=user_id,
                    summary_id=record.id,
                    summary_text=record.summary,
                    metadata=metadata,
                )
                print(f"  RAG 백필 [{i}/{len(records)}] summary_id={record.id}")
            print("RAG 백필 완료!")
        finally:
            db.close()
    except Exception as e:
        print(f"RAG 백필 실패 (무시): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 이벤트"""
    # 시작 시
    global stt_processor, gpt_summarizer, rag_service

    print("모델 초기화 중...")
    stt_processor = STTProcessor()
    gpt_summarizer = GPTSummarizer()
    rag_service = RAGService()
    print("모델 초기화 완료!")

    # 백그라운드에서 미임베딩 요약 백필 실행
    import asyncio
    asyncio.create_task(_backfill_embeddings())

    yield

    # 종료 시 (필요한 경우)
    print("서버 종료 중...")


app = FastAPI(
    title="회의록 봇 API",
    description="음성 파일을 업로드하면 자동으로 회의록을 생성합니다",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정 (웹에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# 공개 엔드포인트 (인증 불필요)
# ============================================

@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "status": "running",
        "message": "회의록 봇 API가 정상 작동 중입니다",
        "endpoints": {
            "POST /transcribe": "음성 파일을 회의록으로 변환",
            "GET /health": "서버 상태 확인"
        }
    }


@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "models_loaded": {
            "stt": stt_processor is not None,
            "gpt": gpt_summarizer is not None
        }
    }


# ============================================
# 인증 엔드포인트
# ============================================

@app.post("/auth/google")
async def google_login(
    token: str = Form(..., description="Google ID 토큰"),
    db: Session = Depends(get_db),
):
    """Google ID 토큰으로 로그인/회원가입 후 JWT 반환"""
    # Google 토큰 검증
    google_info = await verify_google_token(token)

    # 기존 사용자 조회 또는 신규 생성
    user = crud.get_user_by_google_id(db, google_info["google_id"])
    if user:
        user = crud.update_user_login(
            db, user,
            name=google_info["name"],
            picture=google_info["picture"],
        )
    else:
        user = crud.create_user(
            db,
            google_id=google_info["google_id"],
            email=google_info["email"],
            name=google_info["name"],
            picture=google_info["picture"],
        )

    # JWT + Refresh Token 발급
    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(db, user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        }
    }


@app.post("/auth/refresh")
async def refresh_access_token(
    refresh_token: str = Form(..., description="리프레시 토큰"),
    db: Session = Depends(get_db),
):
    """리프레시 토큰으로 새 액세스 토큰 발급"""
    user = verify_refresh_token(db, refresh_token)
    new_access_token = create_access_token(user.id, user.email)
    return {"access_token": new_access_token}


@app.post("/auth/logout")
async def logout_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그아웃 — 리프레시 토큰 무효화"""
    revoke_refresh_token(db, current_user)
    return {"message": "로그아웃 완료"}


@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 반환"""
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "picture": current_user.picture,
        }
    }


# ============================================
# 사용량 조회 엔드포인트
# ============================================

@app.get("/usage")
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자의 사용량 현황 및 잔여 한도 반환"""
    daily_stt_minutes = crud.get_usage_minutes(db, current_user.id, "stt", "daily")
    monthly_stt_minutes = crud.get_usage_minutes(db, current_user.id, "stt", "monthly")
    monthly_cost = crud.get_usage_cost(db, current_user.id, "monthly")

    return {
        "stt": {
            "unit": "minutes",
            "daily": {"used": round(daily_stt_minutes, 1), "limit": DAILY_STT_LIMIT_MINUTES},
            "monthly": {"used": round(monthly_stt_minutes, 1), "limit": MONTHLY_STT_LIMIT_MINUTES},
        },
        "monthly_cost": round(monthly_cost, 4),
    }


# ============================================
# 보호된 엔드포인트 (인증 필요)
# ============================================

@app.post("/transcribe-only")
async def transcribe_only(
    file: UploadFile = File(..., description="음성 파일 (mp3, wav, m4a 등)"),
    whisper_model: WhisperModel = Form(WhisperModel.BASE, description="Whisper API는 단일 모델 사용 (값은 기록용)"),
    audio_duration: float = Form(None, description="오디오 길이 (초)"),
    file_size: int = Form(..., description="파일 크기 (bytes)"),
    project_name: str = Form("", description="프로젝트명"),
    meeting_title: str = Form("", description="회의 제목"),
    attendees: str = Form("", description="참석자 (쉼표로 구분)"),
    keywords: str = Form("", description="관련 키워드 (쉼표로 구분)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    음성 파일을 텍스트로만 변환 (STT만 수행) 및 DB 저장
    """
    # 사용량 한도 확인 (분 단위)
    audio_minutes = (audio_duration or 0) / 60.0
    check_usage_limit(db, current_user.id, audio_minutes=audio_minutes)

    # 파일 확장자 확인
    allowed_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(allowed_extensions)}"
        )

    # 고유한 파일명 생성
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_filename = f"{timestamp}_{unique_id}{file_ext}"
    temp_file_path = os.path.join(UPLOAD_DIR, temp_filename)

    try:
        # 업로드된 파일 저장 (비동기)
        content = await file.read()
        async with aiofiles.open(temp_file_path, "wb") as buffer:
            await buffer.write(content)

        print(f"파일 업로드 완료: {temp_file_path}")

        # STT (음성 -> 텍스트) - 시간 측정
        print("음성을 텍스트로 변환 중...")
        start_time = time.time()
        transcript = await stt_processor.transcribe(temp_file_path)
        stt_time = time.time() - start_time
        print(f"변환 완료 (길이: {len(transcript)}자, 소요 시간: {stt_time:.2f}초)")

        # STT 비용 계산
        stt_cost = calculate_stt_cost(audio_duration)
        print(f"STT 비용: ${stt_cost:.6f}")

        # DB에 저장 (TranscriptRecord 생성)
        transcript_record = crud.create_transcript_record(
            db=db,
            filename=file.filename,
            file_size=file_size,
            transcript=transcript,
            user_id=current_user.id,
            whisper_model=whisper_model.value,
            audio_duration=audio_duration,
            stt_processing_time=stt_time,
            stt_cost=stt_cost,
            project_name=project_name,
            meeting_title=meeting_title,
            attendees=attendees,
            keywords=keywords
        )
        print(f"DB 저장 완료 (Transcript ID: {transcript_record.id})")

        # 사용량 기록 (분 단위)
        crud.create_usage_record(db, current_user.id, "stt", cost=stt_cost, duration_minutes=audio_minutes)

        return JSONResponse(content={
            "success": True,
            "transcript_id": transcript_record.id,
            "filename": file.filename,
            "transcript": transcript,
            "timestamp": timestamp
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"처리 중 오류 발생: {str(e)}")

    finally:
        # 업로드된 임시 파일 삭제
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print(f"임시 파일 삭제: {temp_file_path}")


@app.post("/summarize")
async def summarize_transcript(
    transcript_id: int = Form(..., description="Transcript 레코드 ID"),
    gpt_model: GPTModel = Form(GPTModel.CLAUDE_SONNET_46, description="사용할 GPT 모델 선택"),
    save_files: bool = Form(True, description="결과 파일을 서버에 저장할지 여부"),
    return_file: bool = Form(False, description="회의록을 텍스트 파일로 다운로드 (true 시 파일 응답, false 시 JSON 응답)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    텍스트를 GPT로 요약하여 회의록 생성 및 새 SummaryRecord 생성
    """

    # DB에서 Transcript 레코드 조회 (소유권 확인)
    transcript_record = crud.get_transcript_record(db, transcript_id, current_user.id)
    if not transcript_record:
        raise HTTPException(status_code=404, detail="Transcript 레코드를 찾을 수 없습니다")

    transcript = transcript_record.transcript
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 회의 맥락 정보 구성
    context = {}
    if transcript_record.project_name:
        context["project_name"] = transcript_record.project_name
    if transcript_record.meeting_title:
        context["meeting_title"] = transcript_record.meeting_title
    if transcript_record.attendees:
        context["attendees"] = transcript_record.attendees
    if transcript_record.keywords:
        context["keywords"] = transcript_record.keywords

    try:
        # RAG: 과거 관련 회의록 검색
        past_context = []
        if rag_service:
            try:
                past_context = await rag_service.retrieve_context(
                    user_id=current_user.id,
                    query_text=transcript[:2000],
                )
                if past_context:
                    print(f"RAG: 과거 회의록 {len(past_context)}개 검색됨")
            except Exception as e:
                print(f"RAG 검색 실패 (무시): {e}")

        # GPT 요약 - 시간 측정
        print(f"GPT ({gpt_model.value})로 회의록 작성 중...")
        start_time = time.time()
        result = await gpt_summarizer.summarize(
            transcript, model=gpt_model.value, context=context or None,
            past_context=past_context or None,
        )
        gpt_time = time.time() - start_time

        summary = result["summary"]
        input_tokens = result["input_tokens"]
        output_tokens = result["output_tokens"]
        llm_cost = calculate_llm_cost(gpt_model.value, input_tokens, output_tokens)
        print(f"회의록 작성 완료! (소요 시간: {gpt_time:.2f}초, 비용: ${llm_cost:.6f})")

        # DB에 새 SummaryRecord 생성 (업데이트가 아닌 생성)
        summary_record = crud.create_summary_record(
            db=db,
            transcript_id=transcript_id,
            summary=summary,
            gpt_model=gpt_model.value,
            gpt_processing_time=gpt_time,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_cost=llm_cost
        )
        print(f"DB 저장 완료 (Summary ID: {summary_record.id}, Transcript ID: {transcript_id})")

        # RAG: 새 요약 임베딩 저장
        if rag_service:
            try:
                metadata = {}
                if transcript_record.meeting_title:
                    metadata["meeting_title"] = transcript_record.meeting_title
                if transcript_record.project_name:
                    metadata["project_name"] = transcript_record.project_name
                await rag_service.embed_and_store(
                    user_id=current_user.id,
                    summary_id=summary_record.id,
                    summary_text=summary,
                    metadata=metadata,
                )
            except Exception as e:
                print(f"RAG 저장 실패 (무시): {e}")

        # 파일 저장 또는 응답 준비
        summary_path = os.path.join(OUTPUT_DIR, f"meeting_minutes_{timestamp}_{unique_id}.txt")
        summary_url = None

        # 회의록 파일 생성 (return_file이 True이거나 save_files가 True인 경우)
        if return_file or save_files:
            async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
                await f.write(summary)
            print(f"회의록 파일 생성: {summary_path}")
            summary_url = upload_file_to_s3(
                summary_path,
                f"summaries/meeting_minutes_{timestamp}_{unique_id}.txt",
                content_type="text/plain"
            )

        # 원본 텍스트 파일 저장 (save_files가 True인 경우에만)
        if save_files:
            transcript_path = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}_{unique_id}.txt")
            async with aiofiles.open(transcript_path, "w", encoding="utf-8") as f:
                await f.write(transcript)
            print(f"원본 텍스트 파일 저장: {transcript_path}")
            transcript_url = upload_file_to_s3(
                transcript_path,
                f"transcripts/transcript_{timestamp}_{unique_id}.txt",
                content_type="text/plain"
            )
        else:
            transcript_path = None
            transcript_url = None

        # return_file이 True이면 파일로 응답
        if return_file:
            return FileResponse(
                path=summary_path,
                media_type="text/plain",
                filename=f"meeting_minutes_{timestamp}.txt",
                headers={
                    "Content-Disposition": f'attachment; filename="meeting_minutes_{timestamp}.txt"'
                }
            )

        # 기본: JSON 응답
        response_data = {
            "success": True,
            "summary_id": summary_record.id,
            "transcript_id": transcript_id,
            "summary": summary,
            "timestamp": timestamp
        }

        if save_files:
            response_data["saved_files"] = {
                "transcript": transcript_path,
                "transcript_url": transcript_url,
                "summary": summary_path,
                "summary_url": summary_url
            }

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"처리 중 오류 발생: {str(e)}")


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(..., description="음성 파일 (mp3, wav, m4a 등)"),
    gpt_model: GPTModel = Form(GPTModel.CLAUDE_SONNET_46, description="사용할 GPT 모델 선택"),
    whisper_model: WhisperModel = Form(WhisperModel.BASE, description="Whisper API는 단일 모델 사용 (값은 기록용)"),
    save_files: bool = Form(True, description="결과 파일을 서버에 저장할지 여부"),
    return_file: bool = Form(False, description="회의록을 텍스트 파일로 다운로드 (true 시 파일 응답, false 시 JSON 응답)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    음성 파일을 업로드하여 회의록 생성 (레거시 엔드포인트, 한번에 처리)
    """
    # 사용량 한도 확인 (레거시 엔드포인트는 audio_duration 없이 호출)
    check_usage_limit(db, current_user.id, audio_minutes=0.0)

    # 파일 확장자 확인
    allowed_extensions = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(allowed_extensions)}"
        )

    # 고유한 파일명 생성
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_filename = f"{timestamp}_{unique_id}{file_ext}"
    temp_file_path = os.path.join(UPLOAD_DIR, temp_filename)

    try:
        # 업로드된 파일 저장 (비동기)
        content = await file.read()
        async with aiofiles.open(temp_file_path, "wb") as buffer:
            await buffer.write(content)

        print(f"파일 업로드 완료: {temp_file_path}")

        # 1단계: STT (음성 -> 텍스트)
        print("음성을 텍스트로 변환 중...")
        transcript = await stt_processor.transcribe(temp_file_path)
        print(f"변환 완료 (길이: {len(transcript)}자)")

        # 사용량 기록 (STT)
        crud.create_usage_record(db, current_user.id, "stt", cost=0.0)

        # 2단계: GPT 요약
        print(f"GPT ({gpt_model.value})로 회의록 작성 중...")
        result = await gpt_summarizer.summarize(transcript, model=gpt_model.value)
        summary = result["summary"]
        print("회의록 작성 완료!")

        # 3단계: 파일 저장 또는 응답 준비
        summary_path = os.path.join(OUTPUT_DIR, f"meeting_minutes_{timestamp}_{unique_id}.txt")
        summary_url = None

        # 회의록 파일 생성 (return_file이 True이거나 save_files가 True인 경우)
        if return_file or save_files:
            async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
                await f.write(summary)
            print(f"회의록 파일 생성: {summary_path}")
            summary_url = upload_file_to_s3(
                summary_path,
                f"summaries/meeting_minutes_{timestamp}_{unique_id}.txt",
                content_type="text/plain"
            )

        # 원본 텍스트 파일 저장 (save_files가 True인 경우에만)
        if save_files:
            transcript_path = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}_{unique_id}.txt")
            async with aiofiles.open(transcript_path, "w", encoding="utf-8") as f:
                await f.write(transcript)
            print(f"원본 텍스트 파일 저장: {transcript_path}")
            transcript_url = upload_file_to_s3(
                transcript_path,
                f"transcripts/transcript_{timestamp}_{unique_id}.txt",
                content_type="text/plain"
            )
        else:
            transcript_path = None
            transcript_url = None

        # return_file이 True이면 파일로 응답
        if return_file:
            return FileResponse(
                path=summary_path,
                media_type="text/plain",
                filename=f"meeting_minutes_{timestamp}.txt",
                headers={
                    "Content-Disposition": f'attachment; filename="meeting_minutes_{timestamp}.txt"'
                }
            )

        # 기본: JSON 응답
        response_data = {
            "success": True,
            "filename": file.filename,
            "transcript": transcript,
            "summary": summary,
            "timestamp": timestamp
        }

        if save_files:
            response_data["saved_files"] = {
                "transcript": transcript_path,
                "transcript_url": transcript_url,
                "summary": summary_path,
                "summary_url": summary_url
            }

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"처리 중 오류 발생: {str(e)}")

    finally:
        # 업로드된 임시 파일 삭제
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print(f"임시 파일 삭제: {temp_file_path}")


@app.delete("/cleanup")
async def cleanup_files(days: int = 7):
    """
    오래된 파일 정리

    Args:
        days: 며칠 이전 파일을 삭제할지 (기본값: 7일)
    """
    try:
        deleted_count = 0
        current_time = datetime.now().timestamp()
        max_age = days * 24 * 60 * 60  # 일을 초로 변환

        for directory in [UPLOAD_DIR, OUTPUT_DIR]:
            for filename in os.listdir(directory):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > max_age:
                        os.remove(file_path)
                        deleted_count += 1

        return {
            "success": True,
            "deleted_files": deleted_count,
            "message": f"{days}일 이전 파일 {deleted_count}개 삭제 완료"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 정리 중 오류 발생: {str(e)}")


# ============================================
# 데이터베이스 조회 엔드포인트 (인증 필요)
# ============================================

@app.get("/transcripts")
async def get_transcripts(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 모든 STT 변환 레코드 조회 (페이지네이션)"""
    records = crud.get_all_transcript_records(db, current_user.id, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/transcripts/{transcript_id}")
async def get_transcript(
    transcript_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 STT 레코드 조회 (소유권 확인)"""
    record = crud.get_transcript_record(db, transcript_id, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Transcript 레코드를 찾을 수 없습니다")
    return {"success": True, "record": record}


@app.get("/transcripts/{transcript_id}/summaries")
async def get_transcript_summaries(
    transcript_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 STT 레코드에 대한 모든 요약 조회 (소유권 확인)"""
    summaries = crud.get_summaries_by_transcript(db, transcript_id, current_user.id)
    return {"success": True, "count": len(summaries), "summaries": summaries}


@app.get("/summaries")
async def get_summaries(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 모든 요약 레코드 조회 (페이지네이션)"""
    records = crud.get_all_summary_records(db, current_user.id, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/summaries/{summary_id}")
async def get_summary(
    summary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 요약 레코드 조회 (소유권 확인)"""
    record = crud.get_summary_record(db, summary_id, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")
    return {"success": True, "record": record}


@app.put("/summaries/{summary_id}")
async def update_summary(
    summary_id: int,
    body: SummaryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약 텍스트 편집 (소유권 확인)"""
    record = crud.update_summary_text(db, summary_id, current_user.id, body.summary)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")
    return {"success": True, "summary_id": record.id, "summary": record.summary}


@app.post("/summaries/{summary_id}/send-email")
async def send_email(
    summary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약 내용을 사용자 이메일로 발송 (소유권 확인)"""
    record = crud.get_summary_record(db, summary_id, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")

    # 이메일 제목: 회의 제목 → 없으면 파일명
    transcript = record.transcript
    title = transcript.meeting_title or transcript.filename
    subject = f"[Summarying!] {title}"

    try:
        await send_summary_email(current_user.email, subject, record.summary)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {e}")

    return {"success": True, "message": f"{current_user.email}로 이메일을 발송했습니다"}


@app.get("/search/transcripts")
async def search_transcripts(
    keyword: str,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """키워드로 사용자의 STT 레코드 검색"""
    records = crud.search_transcript_records(db, current_user.id, keyword, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/search/summaries")
async def search_summaries(
    keyword: str,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """키워드로 사용자의 요약 레코드 검색"""
    records = crud.search_summary_records(db, current_user.id, keyword, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


# ============================================
# 프론트엔드 정적 파일 서빙
# ============================================

# 배포(재시작) 시마다 캐시 버스팅용 버전 생성
_CACHE_VERSION = str(int(time.time()))

# CSS, JS 정적 파일 마운트
app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")
app.mount("/images", StaticFiles(directory="frontend/images"), name="images")


@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    """프론트엔드 메인 페이지 서빙 (캐시 버스팅 + Google Client ID 주입)"""
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # CSS/JS 파일에 버전 쿼리스트링 추가하여 배포 시 캐시 자동 무효화
    html = html.replace('href="css/style.css"', f'href="css/style.css?v={_CACHE_VERSION}"')
    html = html.replace('src="js/app.js"', f'src="js/app.js?v={_CACHE_VERSION}"')
    # Google Client ID 주입
    html = html.replace('__GOOGLE_CLIENT_ID__', os.getenv("GOOGLE_CLIENT_ID", ""))
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
