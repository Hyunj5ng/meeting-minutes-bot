"""
STT 엔드포인트 — 단일 변환(/transcribe-only), 합치기 변환(/transcribe-merge), 파일 정리(/cleanup).

요약(LLM)은 routers/summaries.py의 /summarize가 담당한다.
프론트 워크플로우: 업로드 → /transcribe-only(또는 -merge) → /summarize.
"""
import os
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from core import services
from core.config import (
    ALLOWED_AUDIO_EXTENSIONS,
    MERGE_PART_SEPARATOR,
    OUTPUT_DIR,
    UPLOAD_DIR,
)
from core.schemas import WhisperModel
from core.storage import save_upload_to_path
from core.usage import acquire_stt_slot, calculate_stt_cost, check_usage_limit
from database import get_db
from models import User

router = APIRouter(tags=["transcription"])


def validate_audio_extension(filename: str):
    """확장자 검사. 허용 외 형식이면 400."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다 ({filename}). 허용된 형식: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
        )
    return ext


def resolve_project(db: Session, user_id: int, project_id: int | None, project_name: str):
    """project_id 우선, 없으면 project_name으로 조회/생성.

    반환: (effective_project_id, effective_project_name)
    """
    resolved = None
    if project_id is not None:
        resolved = crud.get_project(db, project_id, user_id)
        if not resolved:
            raise HTTPException(status_code=404, detail="지정한 프로젝트를 찾을 수 없습니다")
    elif project_name and project_name.strip():
        resolved = crud.get_or_create_project_by_name(db, user_id, project_name.strip())

    if resolved:
        return resolved.id, resolved.name
    return None, (project_name or None)


def make_temp_path(ext: str, suffix: str = "") -> tuple[str, str]:
    """충돌 없는 업로드 임시 경로 생성. 반환: (timestamp, path)"""
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return timestamp, os.path.join(UPLOAD_DIR, f"{timestamp}_{unique_id}{suffix}{ext}")


@router.post("/transcribe-only")
async def transcribe_only(
    file: UploadFile = File(..., description="음성 파일 (mp3, wav, m4a 등)"),
    whisper_model: WhisperModel = Form(WhisperModel.BASE, description="Whisper API는 단일 모델 사용 (값은 기록용)"),
    audio_duration: float = Form(None, description="오디오 길이 (초)"),
    file_size: int = Form(..., description="파일 크기 (bytes)"),
    project_id: int = Form(None, description="기존 프로젝트 ID (project_name보다 우선)"),
    project_name: str = Form("", description="프로젝트명 (project_id 없을 때 신규/조회)"),
    meeting_title: str = Form("", description="회의 제목"),
    attendees: str = Form("", description="참석자 (쉼표로 구분)"),
    keywords: str = Form("", description="관련 키워드 (쉼표로 구분)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """음성 파일을 텍스트로만 변환 (STT만 수행) 및 DB 저장"""
    audio_minutes = (audio_duration or 0) / 60.0
    check_usage_limit(db, current_user.id, audio_minutes=audio_minutes)

    # 사용자별 동시 STT 슬롯 점유 (한도 초과 시 429)
    async with acquire_stt_slot(current_user.id):
        ext = validate_audio_extension(file.filename)
        timestamp, temp_file_path = make_temp_path(ext)

        try:
            await save_upload_to_path(file, temp_file_path)
            print(f"파일 업로드 완료: {temp_file_path}")

            print("음성을 텍스트로 변환 중...")
            start_time = time.time()
            transcript = await services.stt_processor.transcribe(temp_file_path)
            stt_time = time.time() - start_time
            print(f"변환 완료 (길이: {len(transcript)}자, 소요 시간: {stt_time:.2f}초)")

            stt_cost = calculate_stt_cost(audio_duration)
            print(f"STT 비용: ${stt_cost:.6f}")

            effective_project_id, effective_project_name = resolve_project(
                db, current_user.id, project_id, project_name
            )

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
                project_id=effective_project_id,
                project_name=effective_project_name,
                meeting_title=meeting_title,
                attendees=attendees,
                keywords=keywords
            )
            print(f"DB 저장 완료 (Transcript ID: {transcript_record.id})")

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
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                print(f"임시 파일 삭제: {temp_file_path}")


@router.post("/transcribe-merge")
async def transcribe_merge(
    files: list[UploadFile] = File(..., description="음성 파일 여러 개 (선택한 순서대로 합쳐짐)"),
    audio_durations: str = Form("", description="각 파일 길이(초) — 쉼표로 구분된 숫자열. 합산하여 사용량 계산"),
    file_sizes: str = Form("", description="각 파일 크기(bytes) — 쉼표로 구분"),
    project_id: int = Form(None),
    project_name: str = Form(""),
    meeting_title: str = Form("", description="회의 제목"),
    attendees: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """여러 음성 파일을 순차 STT → 구분선으로 합쳐 단일 TranscriptRecord 생성.

    같은 회의가 휴식 후 이어진 케이스에 사용. 슬롯은 1개만 점유 (하나의 회의록).
    """
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="합치기 모드는 최소 2개 파일이 필요합니다")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="한 번에 합칠 수 있는 파일은 최대 10개입니다")

    # 길이/크기 파싱 (없으면 0으로 채움)
    def _parse_floats(s: str, n: int) -> list[float]:
        if not s:
            return [0.0] * n
        try:
            parts = [float(x.strip()) for x in s.split(",") if x.strip()]
        except ValueError:
            return [0.0] * n
        if len(parts) < n:
            parts += [0.0] * (n - len(parts))
        return parts[:n]

    durations = _parse_floats(audio_durations, len(files))
    sizes = [int(x) for x in _parse_floats(file_sizes, len(files))]

    total_seconds = sum(durations)
    total_minutes = total_seconds / 60.0
    total_size = sum(sizes)

    check_usage_limit(db, current_user.id, audio_minutes=total_minutes)

    for f in files:
        validate_audio_extension(f.filename)

    # 슬롯 점유 (1개 — 하나의 회의록이므로)
    async with acquire_stt_slot(current_user.id):
        temp_paths: list[str] = []
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            for idx, f in enumerate(files):
                ext = os.path.splitext(f.filename)[1].lower()
                _, temp_path = make_temp_path(ext, suffix=f"_part{idx + 1}")
                await save_upload_to_path(f, temp_path)
                temp_paths.append(temp_path)
                print(f"[merge] 파트 {idx + 1}/{len(files)} 업로드 완료: {temp_path}")

            # 순차 STT
            transcripts: list[str] = []
            total_stt_time = 0.0
            for idx, temp_path in enumerate(temp_paths):
                print(f"[merge] 파트 {idx + 1} STT 시작...")
                t0 = time.time()
                text = await services.stt_processor.transcribe(temp_path)
                stt_time = time.time() - t0
                total_stt_time += stt_time
                transcripts.append(text)
                print(f"[merge] 파트 {idx + 1} 변환 완료 ({len(text)}자, {stt_time:.2f}초)")

            merged_transcript = MERGE_PART_SEPARATOR.join(transcripts)
            total_cost = calculate_stt_cost(total_seconds)

            effective_project_id, effective_project_name = resolve_project(
                db, current_user.id, project_id, project_name
            )

            # 합쳐서 단일 레코드 생성. filename은 파트 개수 명시
            display_filename = f"{files[0].filename} 외 {len(files) - 1}개 (합침)"
            transcript_record = crud.create_transcript_record(
                db=db,
                filename=display_filename,
                file_size=total_size,
                transcript=merged_transcript,
                user_id=current_user.id,
                whisper_model="base",
                audio_duration=total_seconds,
                stt_processing_time=total_stt_time,
                stt_cost=total_cost,
                project_id=effective_project_id,
                project_name=effective_project_name,
                meeting_title=meeting_title,
                attendees=attendees,
            )
            print(f"[merge] DB 저장 완료 (Transcript ID: {transcript_record.id}, 총 {len(files)}개 파트 합침)")

            crud.create_usage_record(db, current_user.id, "stt", cost=total_cost, duration_minutes=total_minutes)

            return JSONResponse(content={
                "success": True,
                "transcript_id": transcript_record.id,
                "filename": display_filename,
                "transcript": merged_transcript,
                "timestamp": timestamp,
                "parts": len(files),
            })

        except HTTPException:
            raise
        except Exception as e:
            print(f"[merge] 오류 발생: {str(e)}")
            raise HTTPException(status_code=500, detail=f"합치기 처리 중 오류 발생: {str(e)}")
        finally:
            for p in temp_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass


@router.delete("/cleanup")
async def cleanup_files(
    days: int = 7,
    current_user: User = Depends(get_current_user),
):
    """오래된 업로드/출력 파일 정리 (인증 필요)

    Args:
        days: 며칠 이전 파일을 삭제할지 (기본값: 7일)
    """
    try:
        deleted_count = 0
        current_time = datetime.now().timestamp()
        max_age = days * 24 * 60 * 60

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
