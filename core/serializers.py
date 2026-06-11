"""
응답 직렬화 헬퍼 — 여러 라우터가 공유하는 dict 변환.
"""


def serialize_summary_for_list(record) -> dict:
    """대시보드 목록용 요약 직렬화 (transcript 메타 + 버전 수 포함)"""
    transcript = record.transcript
    version_count = len(record.versions) if record.versions is not None else 1
    return {
        "id": record.id,
        "transcript_id": record.transcript_id,
        "gpt_model": record.gpt_model,
        "summary_preview": (record.summary or "")[:200],
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "version_count": version_count,
        "is_edited": version_count > 1,
        "filename": transcript.filename if transcript else None,
        "meeting_title": transcript.meeting_title if transcript else None,
        "project_name": transcript.project_name if transcript else None,
    }


def serialize_project(project, summary_count: int = 0, context_count: int = 0) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "summary_count": summary_count,
        "context_count": context_count,
    }


def serialize_context_entry(entry) -> dict:
    return {
        "id": entry.id,
        "term": entry.term,
        "correction": entry.correction,
        "note": entry.note,
        "project_id": entry.project_id,
        "source": entry.source,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }
