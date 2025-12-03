"""
CRUD (Create, Read, Update, Delete) 작업
"""
from sqlalchemy.orm import Session
from models import TranscriptRecord, SummaryRecord
from typing import List, Optional


# ========== TranscriptRecord CRUD ==========

def create_transcript_record(
    db: Session,
    filename: str,
    file_size: int,
    transcript: str,
    whisper_model: str = "base",
    audio_duration: Optional[float] = None,
    stt_processing_time: Optional[float] = None
) -> TranscriptRecord:
    """새 STT 변환 레코드 생성"""
    record = TranscriptRecord(
        filename=filename,
        file_size=file_size,
        audio_duration=audio_duration,
        transcript=transcript,
        whisper_model=whisper_model,
        stt_processing_time=stt_processing_time
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_transcript_record(db: Session, transcript_id: int) -> Optional[TranscriptRecord]:
    """특정 STT 레코드 조회"""
    return db.query(TranscriptRecord).filter(TranscriptRecord.id == transcript_id).first()


def get_all_transcript_records(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[TranscriptRecord]:
    """모든 STT 레코드 조회 (페이지네이션)"""
    return db.query(TranscriptRecord).order_by(
        TranscriptRecord.created_at.desc()
    ).offset(skip).limit(limit).all()


def delete_transcript_record(db: Session, transcript_id: int) -> bool:
    """STT 레코드 삭제 (cascade로 관련 summary도 삭제됨)"""
    record = db.query(TranscriptRecord).filter(TranscriptRecord.id == transcript_id).first()
    if record:
        db.delete(record)
        db.commit()
        return True
    return False


def search_transcript_records(
    db: Session,
    keyword: str,
    skip: int = 0,
    limit: int = 100
) -> List[TranscriptRecord]:
    """키워드로 STT 레코드 검색 (파일명 또는 내용)"""
    search_pattern = f"%{keyword}%"
    return db.query(TranscriptRecord).filter(
        (TranscriptRecord.filename.ilike(search_pattern)) |
        (TranscriptRecord.transcript.ilike(search_pattern))
    ).order_by(TranscriptRecord.created_at.desc()).offset(skip).limit(limit).all()


# ========== SummaryRecord CRUD ==========

def create_summary_record(
    db: Session,
    transcript_id: int,
    summary: str,
    gpt_model: str,
    gpt_processing_time: Optional[float] = None
) -> SummaryRecord:
    """새 GPT 요약 레코드 생성"""
    record = SummaryRecord(
        transcript_id=transcript_id,
        summary=summary,
        gpt_model=gpt_model,
        gpt_processing_time=gpt_processing_time
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_summary_record(db: Session, summary_id: int) -> Optional[SummaryRecord]:
    """특정 요약 레코드 조회"""
    return db.query(SummaryRecord).filter(SummaryRecord.id == summary_id).first()


def get_summaries_by_transcript(
    db: Session,
    transcript_id: int
) -> List[SummaryRecord]:
    """특정 STT 레코드에 대한 모든 요약 조회"""
    return db.query(SummaryRecord).filter(
        SummaryRecord.transcript_id == transcript_id
    ).order_by(SummaryRecord.created_at.desc()).all()


def get_all_summary_records(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[SummaryRecord]:
    """모든 요약 레코드 조회 (페이지네이션)"""
    return db.query(SummaryRecord).order_by(
        SummaryRecord.created_at.desc()
    ).offset(skip).limit(limit).all()


def delete_summary_record(db: Session, summary_id: int) -> bool:
    """요약 레코드 삭제"""
    record = db.query(SummaryRecord).filter(SummaryRecord.id == summary_id).first()
    if record:
        db.delete(record)
        db.commit()
        return True
    return False


def search_summary_records(
    db: Session,
    keyword: str,
    skip: int = 0,
    limit: int = 100
) -> List[SummaryRecord]:
    """키워드로 요약 레코드 검색"""
    search_pattern = f"%{keyword}%"
    return db.query(SummaryRecord).filter(
        SummaryRecord.summary.ilike(search_pattern)
    ).order_by(SummaryRecord.created_at.desc()).offset(skip).limit(limit).all()
