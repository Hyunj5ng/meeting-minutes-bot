"""
프로젝트 CRUD + 최근 참석자 자동완성.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from core.schemas import ProjectCreateRequest, ProjectUpdateRequest
from core.serializers import (
    serialize_context_entry,
    serialize_project,
    serialize_summary_for_list,
)
from database import get_db
from models import SummaryRecord, TranscriptRecord, User

router = APIRouter(tags=["projects"])


@router.get("/me/recent-attendees")
async def get_recent_attendees(
    project_id: Optional[int] = None,
    q: str = "",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사용자가 과거 회의록에 입력했던 참석자 이름을 최근순으로 반환.

    - project_id 지정 시 해당 프로젝트 사용자를 우선 정렬
    - q 지정 시 부분 일치(대소문자 무시)로 필터
    """
    names = crud.get_recent_attendees(db, current_user.id, project_id=project_id)
    q_norm = (q or "").strip().lower()
    if q_norm:
        names = [n for n in names if q_norm in n.lower()]
    if limit and limit > 0:
        names = names[:limit]
    return {"success": True, "attendees": names}


@router.get("/projects")
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사용자의 모든 프로젝트 (회의록 수 / 컨텍스트 수 포함)"""
    projects = crud.get_all_projects(db, current_user.id)
    summary_counts = crud.get_project_summary_counts(db, current_user.id)
    return {
        "success": True,
        "count": len(projects),
        "projects": [
            serialize_project(
                p,
                summary_count=summary_counts.get(p.id, 0),
                context_count=len(p.context_entries) if p.context_entries is not None else 0,
            )
            for p in projects
        ],
    }


@router.post("/projects")
async def create_project(
    body: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """새 프로젝트 생성"""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="프로젝트명을 입력해주세요")
    project = crud.create_project(
        db, user_id=current_user.id, name=name, description=body.description
    )
    return {"success": True, "project": serialize_project(project)}


@router.get("/projects/{project_id}")
async def get_project_detail(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """프로젝트 상세: 메타 + 회의록 요약 목록 + 컨텍스트 엔트리"""
    project = crud.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    # 이 프로젝트에 속한 요약들 (최신순)
    summaries = db.query(SummaryRecord).join(TranscriptRecord).filter(
        TranscriptRecord.user_id == current_user.id,
        TranscriptRecord.project_id == project_id,
    ).order_by(SummaryRecord.created_at.desc()).limit(100).all()

    contexts = crud.list_context_entries(
        db, current_user.id, scope="project", project_id=project_id
    )

    return {
        "success": True,
        "project": serialize_project(
            project,
            summary_count=len(summaries),
            context_count=len(contexts),
            include_memory=True,
        ),
        "summaries": [serialize_summary_for_list(r) for r in summaries],
        "contexts": [serialize_context_entry(c) for c in contexts],
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    body: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """프로젝트 정보 수정 (name/description/memory — 넘긴 필드만 갱신)"""
    project = crud.update_project(
        db,
        project_id=project_id,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        memory=body.memory,
    )
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return {"success": True, "project": serialize_project(project, include_memory=True)}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """프로젝트 삭제 (소속 회의록의 project_id는 NULL로 풀림)"""
    ok = crud.delete_project(db, project_id=project_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return {"success": True}
