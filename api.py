from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from enum import Enum
from sqlalchemy.orm import Session
import os
import shutil
from datetime import datetime
from stt_module import STTProcessor
from gpt_summarizer import GPTSummarizer
import uuid
import time

# 데이터베이스 관련 임포트
from database import get_db, engine, Base
from models import TranscriptRecord, SummaryRecord
import crud


# GPT 모델 선택을 위한 Enum
class GPTModel(str, Enum):
    GPT_51_2025 = "gpt-5.1-2025-11-13"
    GPT_50 = "gpt-5-2025-08-07"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4O = "gpt-4o"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_35_TURBO = "gpt-3.5-turbo"


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

# 업로드 및 출력 디렉토리
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 이벤트"""
    # 시작 시
    global stt_processor, gpt_summarizer
    print("모델 초기화 중...")
    stt_processor = STTProcessor(model_size="base")
    gpt_summarizer = GPTSummarizer()
    print("모델 초기화 완료!")

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


@app.post("/transcribe-only")
async def transcribe_only(
    file: UploadFile = File(..., description="음성 파일 (mp3, wav, m4a 등)"),
    whisper_model: WhisperModel = Form(WhisperModel.BASE, description="사용할 Whisper 모델 선택 (현재 세션에서는 서버 시작시 설정된 모델 사용)"),
    audio_duration: float = Form(None, description="오디오 길이 (초)"),
    file_size: int = Form(..., description="파일 크기 (bytes)"),
    db: Session = Depends(get_db)
):
    """
    음성 파일을 텍스트로만 변환 (STT만 수행) 및 DB 저장

    Args:
        file: 음성 파일
        whisper_model: Whisper 모델 선택 (참고용, 서버 재시작 필요)
        audio_duration: 오디오 길이 (초)
        file_size: 파일 크기 (bytes)
        db: 데이터베이스 세션

    Returns:
        JSON 응답 (transcript 및 record_id 포함)
    """
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
        # 업로드된 파일 저장
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"파일 업로드 완료: {temp_file_path}")

        # STT (음성 -> 텍스트) - 시간 측정
        print("음성을 텍스트로 변환 중...")
        start_time = time.time()
        transcript = stt_processor.transcribe(temp_file_path)
        stt_time = time.time() - start_time
        print(f"변환 완료 (길이: {len(transcript)}자, 소요 시간: {stt_time:.2f}초)")

        # DB에 저장 (TranscriptRecord 생성)
        transcript_record = crud.create_transcript_record(
            db=db,
            filename=file.filename,
            file_size=file_size,
            transcript=transcript,
            whisper_model=whisper_model.value,
            audio_duration=audio_duration,
            stt_processing_time=stt_time
        )
        print(f"DB 저장 완료 (Transcript ID: {transcript_record.id})")

        return JSONResponse(content={
            "success": True,
            "transcript_id": transcript_record.id,
            "filename": file.filename,
            "transcript": transcript,
            "timestamp": timestamp
        })

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
    gpt_model: GPTModel = Form(GPTModel.GPT_4O_MINI, description="사용할 GPT 모델 선택"),
    save_files: bool = Form(True, description="결과 파일을 서버에 저장할지 여부"),
    return_file: bool = Form(False, description="회의록을 텍스트 파일로 다운로드 (true 시 파일 응답, false 시 JSON 응답)"),
    db: Session = Depends(get_db)
):
    """
    텍스트를 GPT로 요약하여 회의록 생성 및 새 SummaryRecord 생성

    Args:
        transcript_id: Transcript 레코드 ID (STT 단계에서 생성된 ID)
        gpt_model: GPT 모델 선택 (기본값: gpt-4o-mini)
        save_files: 결과를 파일로 저장할지 여부 (기본값: True)
        return_file: True이면 회의록 텍스트 파일로 응답, False이면 JSON으로 응답 (기본값: False)
        db: 데이터베이스 세션

    Returns:
        JSON 응답 또는 텍스트 파일 다운로드
    """
    # DB에서 Transcript 레코드 조회
    transcript_record = crud.get_transcript_record(db, transcript_id)
    if not transcript_record:
        raise HTTPException(status_code=404, detail="Transcript 레코드를 찾을 수 없습니다")

    transcript = transcript_record.transcript
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # GPT 요약 - 시간 측정
        print(f"GPT ({gpt_model.value})로 회의록 작성 중...")
        start_time = time.time()
        summary = gpt_summarizer.summarize(transcript, model=gpt_model.value)
        gpt_time = time.time() - start_time
        print(f"회의록 작성 완료! (소요 시간: {gpt_time:.2f}초)")

        # DB에 새 SummaryRecord 생성 (업데이트가 아닌 생성)
        summary_record = crud.create_summary_record(
            db=db,
            transcript_id=transcript_id,
            summary=summary,
            gpt_model=gpt_model.value,
            gpt_processing_time=gpt_time
        )
        print(f"DB 저장 완료 (Summary ID: {summary_record.id}, Transcript ID: {transcript_id})")

        # 파일 저장 또는 응답 준비
        summary_path = os.path.join(OUTPUT_DIR, f"meeting_minutes_{timestamp}_{unique_id}.txt")

        # 회의록 파일 생성 (return_file이 True이거나 save_files가 True인 경우)
        if return_file or save_files:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"회의록 파일 생성: {summary_path}")

        # 원본 텍스트 파일 저장 (save_files가 True인 경우에만)
        if save_files:
            transcript_path = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}_{unique_id}.txt")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"원본 텍스트 파일 저장: {transcript_path}")

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
                "summary": summary_path
            }

        return JSONResponse(content=response_data)

    except Exception as e:
        print(f"오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"처리 중 오류 발생: {str(e)}")


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(..., description="음성 파일 (mp3, wav, m4a 등)"),
    gpt_model: GPTModel = Form(GPTModel.GPT_4O_MINI, description="사용할 GPT 모델 선택"),
    whisper_model: WhisperModel = Form(WhisperModel.BASE, description="사용할 Whisper 모델 선택 (현재 세션에서는 서버 시작시 설정된 모델 사용)"),
    save_files: bool = Form(True, description="결과 파일을 서버에 저장할지 여부"),
    return_file: bool = Form(False, description="회의록을 텍스트 파일로 다운로드 (true 시 파일 응답, false 시 JSON 응답)")
):
    """
    음성 파일을 업로드하여 회의록 생성 (레거시 엔드포인트, 한번에 처리)

    Args:
        file: 음성 파일
        gpt_model: GPT 모델 선택 (기본값: gpt-4o-mini)
        whisper_model: Whisper 모델 선택 (참고용, 서버 재시작 필요)
        save_files: 결과를 파일로 저장할지 여부 (기본값: True)
        return_file: True이면 회의록 텍스트 파일로 응답, False이면 JSON으로 응답 (기본값: False)

    Returns:
        JSON 응답 또는 텍스트 파일 다운로드
    """
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
        # 업로드된 파일 저장
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"파일 업로드 완료: {temp_file_path}")

        # 1단계: STT (음성 -> 텍스트)
        print("음성을 텍스트로 변환 중...")
        transcript = stt_processor.transcribe(temp_file_path)
        print(f"변환 완료 (길이: {len(transcript)}자)")

        # 2단계: GPT 요약
        print(f"GPT ({gpt_model.value})로 회의록 작성 중...")
        summary = gpt_summarizer.summarize(transcript, model=gpt_model.value)
        print("회의록 작성 완료!")

        # 3단계: 파일 저장 또는 응답 준비
        summary_path = os.path.join(OUTPUT_DIR, f"meeting_minutes_{timestamp}_{unique_id}.txt")

        # 회의록 파일 생성 (return_file이 True이거나 save_files가 True인 경우)
        if return_file or save_files:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"회의록 파일 생성: {summary_path}")

        # 원본 텍스트 파일 저장 (save_files가 True인 경우에만)
        if save_files:
            transcript_path = os.path.join(OUTPUT_DIR, f"transcript_{timestamp}_{unique_id}.txt")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"원본 텍스트 파일 저장: {transcript_path}")

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
                "summary": summary_path
            }

        return JSONResponse(content=response_data)

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
# 데이터베이스 조회 엔드포인트
# ============================================

@app.get("/transcripts")
async def get_transcripts(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """모든 STT 변환 레코드 조회 (페이지네이션)"""
    records = crud.get_all_transcript_records(db, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/transcripts/{transcript_id}")
async def get_transcript(transcript_id: int, db: Session = Depends(get_db)):
    """특정 STT 레코드 조회"""
    record = crud.get_transcript_record(db, transcript_id)
    if not record:
        raise HTTPException(status_code=404, detail="Transcript 레코드를 찾을 수 없습니다")
    return {"success": True, "record": record}


@app.get("/transcripts/{transcript_id}/summaries")
async def get_transcript_summaries(transcript_id: int, db: Session = Depends(get_db)):
    """특정 STT 레코드에 대한 모든 요약 조회"""
    summaries = crud.get_summaries_by_transcript(db, transcript_id)
    return {"success": True, "count": len(summaries), "summaries": summaries}


@app.get("/summaries")
async def get_summaries(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """모든 요약 레코드 조회 (페이지네이션)"""
    records = crud.get_all_summary_records(db, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/summaries/{summary_id}")
async def get_summary(summary_id: int, db: Session = Depends(get_db)):
    """특정 요약 레코드 조회"""
    record = crud.get_summary_record(db, summary_id)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")
    return {"success": True, "record": record}


@app.get("/search/transcripts")
async def search_transcripts(
    keyword: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """키워드로 STT 레코드 검색"""
    records = crud.search_transcript_records(db, keyword, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@app.get("/search/summaries")
async def search_summaries(
    keyword: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """키워드로 요약 레코드 검색"""
    records = crud.search_summary_records(db, keyword, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
