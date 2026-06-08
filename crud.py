"""
CRUD (Create, Read, Update, Delete) 작업
"""
import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from models import (
    TranscriptRecord,
    SummaryRecord,
    SummaryVersion,
    User,
    UsageRecord,
    Project,
    ContextEntry,
    VERSION_SOURCE_AI_INITIAL,
    VERSION_SOURCE_USER_EDIT,
    CONTEXT_SOURCE_MANUAL,
    CONTEXT_SOURCE_AUTO,
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
    project_id: Optional[int] = None,
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
        project_id=project_id,
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


def get_recent_attendees(
    db: Session,
    user_id: int,
    project_id: Optional[int] = None,
    scan_limit: int = 200,
) -> List[str]:
    """사용자의 최근 회의록에서 참석자 이름을 최근순·고유로 추출.

    project_id가 주어지면 그 프로젝트 우선으로 정렬하되, 부족하면 전체에서 보강.
    이름은 콤마/세미콜론/슬래시 등으로 분리하고 trim하여 중복 제거.
    """
    query = db.query(TranscriptRecord.attendees, TranscriptRecord.project_id).filter(
        TranscriptRecord.user_id == user_id,
        TranscriptRecord.attendees.isnot(None),
        TranscriptRecord.attendees != "",
    ).order_by(TranscriptRecord.created_at.desc()).limit(scan_limit)

    rows = query.all()

    in_project: List[str] = []
    other: List[str] = []
    seen = set()

    for attendees_str, row_project_id in rows:
        if not attendees_str:
            continue
        # 콤마/세미콜론/슬래시 모두 구분자로 처리
        parts = re.split(r"[,;/\n]", attendees_str)
        for raw in parts:
            name = raw.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            if project_id is not None and row_project_id == project_id:
                in_project.append(name)
            else:
                other.append(name)

    return in_project + other


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


# ========== Project CRUD ==========

def create_project(
    db: Session,
    user_id: int,
    name: str,
    description: Optional[str] = None,
) -> Project:
    """새 프로젝트 생성"""
    project = Project(user_id=user_id, name=name, description=description or None)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_project(db: Session, project_id: int, user_id: int) -> Optional[Project]:
    """프로젝트 단건 조회 (소유권 확인)"""
    return db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user_id,
    ).first()


def get_or_create_project_by_name(
    db: Session,
    user_id: int,
    name: str,
) -> Optional[Project]:
    """이름으로 프로젝트 조회, 없으면 생성. 빈 문자열이면 None 반환."""
    if not name or not name.strip():
        return None
    name = name.strip()
    project = db.query(Project).filter(
        Project.user_id == user_id,
        Project.name == name,
    ).first()
    if project:
        return project
    return create_project(db, user_id=user_id, name=name)


def get_all_projects(db: Session, user_id: int) -> List[Project]:
    """사용자의 모든 프로젝트 (최근 수정순)"""
    return db.query(Project).filter(
        Project.user_id == user_id,
    ).order_by(Project.updated_at.desc()).all()


def update_project(
    db: Session,
    project_id: int,
    user_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Project]:
    """프로젝트 수정 (소유권 확인)"""
    project = get_project(db, project_id, user_id)
    if not project:
        return None
    if name is not None and name.strip():
        project.name = name.strip()
    if description is not None:
        project.description = description or None
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int, user_id: int) -> bool:
    """프로젝트 삭제 (소유권 확인). transcript의 project_id는 SET NULL로 정리됨."""
    project = get_project(db, project_id, user_id)
    if not project:
        return False
    db.delete(project)
    db.commit()
    return True


def get_project_summary_counts(db: Session, user_id: int) -> dict:
    """프로젝트별 회의록 수 집계 (id → count)"""
    rows = db.query(
        TranscriptRecord.project_id,
        sa_func.count(SummaryRecord.id),
    ).join(
        SummaryRecord, SummaryRecord.transcript_id == TranscriptRecord.id
    ).filter(
        TranscriptRecord.user_id == user_id,
        TranscriptRecord.project_id.isnot(None),
    ).group_by(TranscriptRecord.project_id).all()
    return {pid: cnt for pid, cnt in rows}


# ========== ContextEntry CRUD ==========

def create_context_entry(
    db: Session,
    user_id: int,
    term: str,
    correction: str,
    project_id: Optional[int] = None,
    note: Optional[str] = None,
    source: str = CONTEXT_SOURCE_MANUAL,
) -> Optional[ContextEntry]:
    """컨텍스트 엔트리 생성.
    project_id가 지정된 경우 해당 프로젝트가 user 소유인지 확인."""
    if project_id is not None:
        project = get_project(db, project_id, user_id)
        if not project:
            return None

    entry = ContextEntry(
        user_id=user_id,
        project_id=project_id,
        term=term.strip(),
        correction=correction.strip(),
        note=(note or "").strip() or None,
        source=source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_context_entry(db: Session, entry_id: int, user_id: int) -> Optional[ContextEntry]:
    """컨텍스트 엔트리 단건 조회 (소유권 확인)"""
    return db.query(ContextEntry).filter(
        ContextEntry.id == entry_id,
        ContextEntry.user_id == user_id,
    ).first()


def list_context_entries(
    db: Session,
    user_id: int,
    scope: str = "personal",
    project_id: Optional[int] = None,
) -> List[ContextEntry]:
    """컨텍스트 엔트리 목록.
    scope='personal' → project_id IS NULL
    scope='project' → project_id == 지정값 (소유권 검증 후)
    scope='all' → user의 모든 엔트리
    """
    q = db.query(ContextEntry).filter(ContextEntry.user_id == user_id)
    if scope == "personal":
        q = q.filter(ContextEntry.project_id.is_(None))
    elif scope == "project":
        if project_id is None:
            return []
        # 소유권 검증
        if not get_project(db, project_id, user_id):
            return []
        q = q.filter(ContextEntry.project_id == project_id)
    # 'all'은 추가 필터 없음
    return q.order_by(ContextEntry.updated_at.desc()).all()


def update_context_entry(
    db: Session,
    entry_id: int,
    user_id: int,
    term: Optional[str] = None,
    correction: Optional[str] = None,
    note: Optional[str] = None,
) -> Optional[ContextEntry]:
    """컨텍스트 엔트리 수정 (소유권 확인). 수정 시 source는 manual로 승격."""
    entry = get_context_entry(db, entry_id, user_id)
    if not entry:
        return None
    if term is not None and term.strip():
        entry.term = term.strip()
    if correction is not None and correction.strip():
        entry.correction = correction.strip()
    if note is not None:
        entry.note = (note or "").strip() or None
    # 사용자가 직접 수정한 엔트리는 manual로 승격 (auto 분류 → 사용자 검증됨)
    entry.source = CONTEXT_SOURCE_MANUAL
    db.commit()
    db.refresh(entry)
    return entry


def delete_context_entry(db: Session, entry_id: int, user_id: int) -> bool:
    """컨텍스트 엔트리 삭제 (소유권 확인)"""
    entry = get_context_entry(db, entry_id, user_id)
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


def find_context_entry_by_term(
    db: Session,
    user_id: int,
    project_id: Optional[int],
    term: str,
) -> Optional[ContextEntry]:
    """동일 term의 엔트리 조회 (자동 추출 시 중복 방지용).
    project_id IS NULL과 NOT NULL을 명시적으로 구분한다."""
    q = db.query(ContextEntry).filter(
        ContextEntry.user_id == user_id,
        ContextEntry.term == term,
    )
    if project_id is None:
        q = q.filter(ContextEntry.project_id.is_(None))
    else:
        q = q.filter(ContextEntry.project_id == project_id)
    return q.first()


def upsert_auto_context_entry(
    db: Session,
    user_id: int,
    project_id: Optional[int],
    term: str,
    correction: str,
    note: Optional[str] = None,
) -> Optional[ContextEntry]:
    """자동 추출용 업서트.
    - 동일 term이 있으면: 사용자가 수정한 manual 엔트리는 건드리지 않음 (덮어쓰지 않음).
      auto 엔트리이고 correction이 다르면 갱신.
    - 없으면: source='auto'로 신규 생성."""
    term = (term or "").strip()
    correction = (correction or "").strip()
    if not term or not correction:
        return None

    existing = find_context_entry_by_term(db, user_id, project_id, term)
    if existing:
        if existing.source == CONTEXT_SOURCE_MANUAL:
            # 사용자 검증된 항목은 덮어쓰지 않음
            return existing
        # auto 엔트리 — 정보가 변경됐다면 갱신
        if existing.correction != correction or (note and existing.note != note):
            existing.correction = correction
            if note:
                existing.note = note.strip() or None
            db.commit()
            db.refresh(existing)
        return existing

    return create_context_entry(
        db,
        user_id=user_id,
        term=term,
        correction=correction,
        project_id=project_id,
        note=note,
        source=CONTEXT_SOURCE_AUTO,
    )


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
