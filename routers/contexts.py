"""
컨텍스트 글로서리 엔드포인트 (개인/프로젝트 용어·표기 교정 사전).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from core.schemas import ContextEntryCreateRequest, ContextEntryUpdateRequest
from core.serializers import serialize_context_entry
from database import get_db
from models import User

router = APIRouter(prefix="/contexts", tags=["contexts"])


@router.get("")
async def list_contexts(
    scope: str = Query("personal", description="personal | project | all"),
    project_id: int = Query(None, description="scope=project일 때 필수"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """컨텍스트 글로서리 목록 (개인 또는 특정 프로젝트)"""
    if scope not in ("personal", "project", "all"):
        raise HTTPException(status_code=400, detail="scope는 personal | project | all 중 하나여야 합니다")
    if scope == "project" and project_id is None:
        raise HTTPException(status_code=400, detail="scope=project인 경우 project_id가 필요합니다")
    entries = crud.list_context_entries(
        db, current_user.id, scope=scope, project_id=project_id
    )
    return {
        "success": True,
        "count": len(entries),
        "entries": [serialize_context_entry(e) for e in entries],
    }


@router.post("")
async def create_context(
    body: ContextEntryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """새 컨텍스트 엔트리 생성 (개인 또는 프로젝트)"""
    if not body.term.strip() or not body.correction.strip():
        raise HTTPException(status_code=400, detail="term과 correction은 비울 수 없습니다")
    entry = crud.create_context_entry(
        db,
        user_id=current_user.id,
        term=body.term,
        correction=body.correction,
        project_id=body.project_id,
        note=body.note,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="지정한 프로젝트를 찾을 수 없습니다")
    return {"success": True, "entry": serialize_context_entry(entry)}


@router.put("/{entry_id}")
async def update_context(
    entry_id: int,
    body: ContextEntryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """컨텍스트 엔트리 수정 (수정 시 source는 manual로 승격)"""
    entry = crud.update_context_entry(
        db,
        entry_id=entry_id,
        user_id=current_user.id,
        term=body.term,
        correction=body.correction,
        note=body.note,
    )
    if not entry:
        raise HTTPException(status_code=404, detail="컨텍스트 엔트리를 찾을 수 없습니다")
    return {"success": True, "entry": serialize_context_entry(entry)}


@router.delete("/{entry_id}")
async def delete_context(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """컨텍스트 엔트리 삭제"""
    ok = crud.delete_context_entry(db, entry_id=entry_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="컨텍스트 엔트리를 찾을 수 없습니다")
    return {"success": True}
