"""
CRUD (Create, Read, Update, Delete) 작업
"""
from sqlalchemy.orm import Session
from models import MeetingRecord
from typing import List, Optional


def create_meeting_record(
    db: Session,
    filename: str,
    file_size: int,
    transcript: str,
    whisper_model: str = "base",
    audio_duration: Optional[float] = None,
    stt_processing_time: Optional[float] = None
) -> MeetingRecord:
    """새 회의록 레코드 생성 (STT 완료 시)"""
    record = MeetingRecord(
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


def update_meeting_summary(
    db: Session,
    record_id: int,
    summary: str,
    gpt_model: str,
    gpt_processing_time: Optional[float] = None
) -> MeetingRecord:
    """회의록 요약 업데이트 (GPT 완료 시)"""
    record = db.query(MeetingRecord).filter(MeetingRecord.id == record_id).first()
    if record:
        record.summary = summary
        record.gpt_model = gpt_model
        record.gpt_processing_time = gpt_processing_time
        db.commit()
        db.refresh(record)
    return record


def get_meeting_record(db: Session, record_id: int) -> Optional[MeetingRecord]:
    """특정 회의록 레코드 조회"""
    return db.query(MeetingRecord).filter(MeetingRecord.id == record_id).first()


def get_all_meeting_records(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[MeetingRecord]:
    """모든 회의록 레코드 조회 (페이지네이션)"""
    return db.query(MeetingRecord).order_by(
        MeetingRecord.created_at.desc()
    ).offset(skip).limit(limit).all()


def delete_meeting_record(db: Session, record_id: int) -> bool:
    """회의록 레코드 삭제"""
    record = db.query(MeetingRecord).filter(MeetingRecord.id == record_id).first()
    if record:
        db.delete(record)
        db.commit()
        return True
    return False


def search_meeting_records(
    db: Session,
    keyword: str,
    skip: int = 0,
    limit: int = 100
) -> List[MeetingRecord]:
    """키워드로 회의록 검색 (파일명 또는 내용)"""
    search_pattern = f"%{keyword}%"
    return db.query(MeetingRecord).filter(
        (MeetingRecord.filename.ilike(search_pattern)) |
        (MeetingRecord.transcript.ilike(search_pattern)) |
        (MeetingRecord.summary.ilike(search_pattern))
    ).order_by(MeetingRecord.created_at.desc()).offset(skip).limit(limit).all()
