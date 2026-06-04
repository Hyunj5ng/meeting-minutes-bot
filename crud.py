"""
CRUD (Create, Read, Update, Delete) 작업
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from models import (
    TranscriptRecord,
    SummaryRecord,
    SummaryVersion,
    User,
    UsageRecord,
    VERSION_SOURCE_AI_INITIAL,
    VERSION_SOURCE_USER_EDIT,
)
from typing import List, Optional


# ========== User CRUD ==========

def get_user_by_google_id(db: Session, google_id: str) -> Optional[User]:
    """Google ID로 사용자 조회"""
    return db.query(User).filter(User.google_id == google_id).first()


def create_user(
    db: Session,
    google_id: str,
    email: str,
    name: str = "",
    picture: str = "",
) -> User:
    """새 사용자 생성"""
    user = User(
        google_id=google_id,
        email=email,
        name=name,
        picture=picture,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_login(
    db: Session,
    user: User,
    name: str = "",
    picture: str = "",
) -> User:
    """로그인 시 사용자 정보 갱신"""
    user.name = name or user.name
    user.picture = picture or user.picture
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


# ========== UsageRecord CRUD ==========

def create_usage_record(
    db: Session,
    user_id: int,
    action_type: str,
    cost: float = 0.0,
    duration_minutes: float = 0.0,
) -> UsageRecord:
    """사용량 기록 생성"""
    record = UsageRecord(
        user_id=user_id,
        action_type=action_type,
        cost=cost,
        duration_minutes=duration_minutes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_usage_count(
    db: Session,
    user_id: int,
    action_type: str,
    period: str = "daily",
) -> int:
    """특정 기간 내 사용 횟수 조회 (daily 또는 monthly)"""
    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return db.query(sa_func.count(UsageRecord.id)).filter(
        UsageRecord.user_id == user_id,
        UsageRecord.action_type == action_type,
        UsageRecord.created_at >= start,
    ).scalar() or 0


def get_usage_minutes(
    db: Session,
    user_id: int,
    action_type: str,
    period: str = "daily",
) -> float:
    """특정 기간 내 사용한 총 분(minutes) 조회 (STT용)"""
    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return db.query(
        sa_func.coalesce(sa_func.sum(UsageRecord.duration_minutes), 0.0)
    ).filter(
        UsageRecord.user_id == user_id,
        UsageRecord.action_type == action_type,
        UsageRecord.created_at >= start,
    ).scalar() or 0.0


def get_usage_cost(
    db: Session,
    user_id: int,
    period: str = "monthly",
) -> float:
    """특정 기간 내 총 비용 조회"""
    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return db.query(sa_func.coalesce(sa_func.sum(UsageRecord.cost), 0.0)).filter(
        UsageRecord.user_id == user_id,
        UsageRecord.created_at >= start,
    ).scalar() or 0.0


# ========== TranscriptRecord CRUD ==========

def create_transcript_record(
    db: Session,
    filename: str,
    file_size: int,
    transcript: str,
    user_id: Optional[int] = None,
    whisper_model: str = "base",
    audio_duration: Optional[float] = None,
    stt_processing_time: Optional[float] = None,
    stt_cost: Optional[float] = None,
    project_name: Optional[str] = None,
    meeting_title: Optional[str] = None,
    attendees: Optional[str] = None,
    keywords: Optional[str] = None
) -> TranscriptRecord:
    """새 STT 변환 레코드 생성"""
    record = TranscriptRecord(
        user_id=user_id,
        filename=filename,
        file_size=file_size,
        audio_duration=audio_duration,
        transcript=transcript,
        whisper_model=whisper_model,
        stt_processing_time=stt_processing_time,
        stt_cost=stt_cost,
        project_name=project_name or None,
        meeting_title=meeting_title or None,
        attendees=attendees or None,
        keywords=keywords or None
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_transcript_record(db: Session, transcript_id: int, user_id: int) -> Optional[TranscriptRecord]:
    """특정 STT 레코드 조회 (소유권 확인)"""
    return db.query(TranscriptRecord).filter(
        TranscriptRecord.id == transcript_id,
        TranscriptRecord.user_id == user_id,
    ).first()


def get_all_transcript_records(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[TranscriptRecord]:
    """사용자의 모든 STT 레코드 조회 (페이지네이션)"""
    return db.query(TranscriptRecord).filter(
        TranscriptRecord.user_id == user_id,
    ).order_by(
        TranscriptRecord.created_at.desc()
    ).offset(skip).limit(limit).all()


def delete_transcript_record(db: Session, transcript_id: int, user_id: int) -> bool:
    """STT 레코드 삭제 (소유권 확인, cascade로 관련 summary도 삭제됨)"""
    record = db.query(TranscriptRecord).filter(
        TranscriptRecord.id == transcript_id,
        TranscriptRecord.user_id == user_id,
    ).first()
    if record:
        db.delete(record)
        db.commit()
        return True
    return False


def search_transcript_records(
    db: Session,
    user_id: int,
    keyword: str,
    skip: int = 0,
    limit: int = 100
) -> List[TranscriptRecord]:
    """키워드로 사용자의 STT 레코드 검색 (파일명 또는 내용)"""
    search_pattern = f"%{keyword}%"
    return db.query(TranscriptRecord).filter(
        TranscriptRecord.user_id == user_id,
        (TranscriptRecord.filename.ilike(search_pattern)) |
        (TranscriptRecord.transcript.ilike(search_pattern))
    ).order_by(TranscriptRecord.created_at.desc()).offset(skip).limit(limit).all()


# ========== SummaryRecord CRUD ==========

def create_summary_record(
    db: Session,
    transcript_id: int,
    summary: str,
    gpt_model: str,
    gpt_processing_time: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    llm_cost: Optional[float] = None
) -> SummaryRecord:
    """새 GPT 요약 레코드 생성 + v1(ai_initial) 버전 동시 생성"""
    record = SummaryRecord(
        transcript_id=transcript_id,
        summary=summary,
        gpt_model=gpt_model,
        gpt_processing_time=gpt_processing_time,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_cost=llm_cost
    )
    db.add(record)
    db.flush()  # record.id 확보

    v1 = SummaryVersion(
        summary_id=record.id,
        version_no=1,
        content=summary,
        source=VERSION_SOURCE_AI_INITIAL,
    )
    db.add(v1)
    db.commit()
    db.refresh(record)
    return record


def get_summary_record(db: Session, summary_id: int, user_id: int) -> Optional[SummaryRecord]:
    """특정 요약 레코드 조회 (transcript 소유권 확인)"""
    return db.query(SummaryRecord).join(TranscriptRecord).filter(
        SummaryRecord.id == summary_id,
        TranscriptRecord.user_id == user_id,
    ).first()


def get_summaries_by_transcript(
    db: Session,
    transcript_id: int,
    user_id: int,
) -> List[SummaryRecord]:
    """특정 STT 레코드에 대한 모든 요약 조회 (소유권 확인)"""
    return db.query(SummaryRecord).join(TranscriptRecord).filter(
        SummaryRecord.transcript_id == transcript_id,
        TranscriptRecord.user_id == user_id,
    ).order_by(SummaryRecord.created_at.desc()).all()


def get_all_summary_records(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[SummaryRecord]:
    """사용자의 모든 요약 레코드 조회 (페이지네이션)"""
    return db.query(SummaryRecord).join(TranscriptRecord).filter(
        TranscriptRecord.user_id == user_id,
    ).order_by(
        SummaryRecord.created_at.desc()
    ).offset(skip).limit(limit).all()


def delete_summary_record(db: Session, summary_id: int, user_id: int) -> bool:
    """요약 레코드 삭제 (소유권 확인)"""
    record = db.query(SummaryRecord).join(TranscriptRecord).filter(
        SummaryRecord.id == summary_id,
        TranscriptRecord.user_id == user_id,
    ).first()
    if record:
        db.delete(record)
        db.commit()
        return True
    return False


def update_summary_text(
    db: Session,
    summary_id: int,
    user_id: int,
    new_summary: str,
) -> Optional[SummaryRecord]:
    """요약 텍스트 업데이트 (소유권 확인).
    이전 본문과 동일하면 새 버전을 만들지 않고 기존 레코드를 그대로 반환한다.
    다르면 user_edit 버전을 append 하고 summary_records.summary는 최신본 포인터로 갱신한다.
    """
    record = db.query(SummaryRecord).join(TranscriptRecord).filter(
        SummaryRecord.id == summary_id,
        TranscriptRecord.user_id == user_id,
    ).first()
    if not record:
        return None

    if record.summary == new_summary:
        return record

    latest_version_no = db.query(sa_func.coalesce(sa_func.max(SummaryVersion.version_no), 0)).filter(
        SummaryVersion.summary_id == summary_id,
    ).scalar() or 0

    next_version = SummaryVersion(
        summary_id=summary_id,
        version_no=latest_version_no + 1,
        content=new_summary,
        source=VERSION_SOURCE_USER_EDIT,
    )
    db.add(next_version)
    record.summary = new_summary
    db.commit()
    db.refresh(record)
    return record


def get_summary_versions(
    db: Session,
    summary_id: int,
    user_id: int,
) -> Optional[List[SummaryVersion]]:
    """특정 요약의 모든 버전 조회 (소유권 확인).
    반환값 None은 권한 없음/존재하지 않음을 의미."""
    summary = db.query(SummaryRecord).join(TranscriptRecord).filter(
        SummaryRecord.id == summary_id,
        TranscriptRecord.user_id == user_id,
    ).first()
    if not summary:
        return None

    return db.query(SummaryVersion).filter(
        SummaryVersion.summary_id == summary_id,
    ).order_by(SummaryVersion.version_no.asc()).all()


def get_summary_version(
    db: Session,
    summary_id: int,
    version_no: int,
    user_id: int,
) -> Optional[SummaryVersion]:
    """특정 버전 단건 조회 (소유권 확인)"""
    return db.query(SummaryVersion).join(
        SummaryRecord, SummaryVersion.summary_id == SummaryRecord.id
    ).join(TranscriptRecord).filter(
        SummaryVersion.summary_id == summary_id,
        SummaryVersion.version_no == version_no,
        TranscriptRecord.user_id == user_id,
    ).first()


def search_summary_records(
    db: Session,
    user_id: int,
    keyword: str,
    skip: int = 0,
    limit: int = 100
) -> List[SummaryRecord]:
    """키워드로 사용자의 요약 레코드 검색 (요약본문/파일명/회의제목/프로젝트명)"""
    search_pattern = f"%{keyword}%"
    return db.query(SummaryRecord).join(TranscriptRecord).filter(
        TranscriptRecord.user_id == user_id,
        (SummaryRecord.summary.ilike(search_pattern)) |
        (TranscriptRecord.filename.ilike(search_pattern)) |
        (TranscriptRecord.meeting_title.ilike(search_pattern)) |
        (TranscriptRecord.project_name.ilike(search_pattern))
    ).order_by(SummaryRecord.created_at.desc()).offset(skip).limit(limit).all()
