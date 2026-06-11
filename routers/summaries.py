"""
요약 생성(/summarize) + 요약/원문 레코드 조회·편집·버전·이메일 발송.
"""
import os
import time
import uuid
from datetime import datetime

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

import context_learner
import crud
import project_memory
from auth import get_current_user
from core import services
from core.config import OUTPUT_DIR
from core.schemas import LLMModel, SummaryProjectUpdateRequest, SummaryUpdateRequest
from core.serializers import serialize_summary_for_list
from core.storage import upload_file_to_s3
from core.usage import calculate_llm_cost
from database import get_db
from email_service import send_summary_email, send_summary_email_background
from models import User

router = APIRouter(tags=["summaries"])


@router.post("/summarize")
async def summarize_transcript(
    background_tasks: BackgroundTasks,
    transcript_id: int = Form(..., description="Transcript 레코드 ID"),
    gpt_model: LLMModel = Form(LLMModel.CLAUDE_SONNET_46, description="사용할 LLM 모델 선택"),
    save_files: bool = Form(True, description="결과 파일을 서버에 저장할지 여부"),
    return_file: bool = Form(False, description="회의록을 텍스트 파일로 다운로드 (true 시 파일 응답, false 시 JSON 응답)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """텍스트를 LLM으로 요약하여 회의록 생성 및 새 SummaryRecord 생성.

    학습 루프: 프로젝트 메모리 주입 → 요약 → 백그라운드로 메모리 갱신.
    회의가 쌓일수록 프로젝트 맥락을 더 잘 기억하게 된다."""

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

    # 글로서리(용어 교정) 구성: 개인 컨텍스트 + (해당 프로젝트의 컨텍스트가 있다면)
    personal_entries = crud.list_context_entries(db, current_user.id, scope="personal", entry_type="term")
    project_entries = []
    if transcript_record.project_id:
        project_entries = crud.list_context_entries(
            db, current_user.id, scope="project", project_id=transcript_record.project_id, entry_type="term"
        )
    # 프로젝트 컨텍스트가 개인 컨텍스트보다 우선 (충돌 시 프로젝트 본을 신뢰)
    glossary = [
        {"term": e.term, "correction": e.correction, "note": e.note}
        for e in (project_entries + personal_entries)
    ]
    if glossary:
        print(f"글로서리 적용: 개인 {len(personal_entries)}건 + 프로젝트 {len(project_entries)}건")

    # 스타일 선호 (수정 패턴에서 학습된 규칙)
    style_entries = crud.list_context_entries(db, current_user.id, scope="all", entry_type="style")
    style_rules = [e.correction for e in style_entries]
    if style_rules:
        print(f"스타일 규칙 적용: {len(style_rules)}건")

    # 프로젝트 누적 메모리
    proj = transcript_record.project
    proj_memory = proj.memory if proj else None
    if proj_memory:
        print(f"프로젝트 메모리 주입: {len(proj_memory)}자")

    try:
        # RAG: 과거 관련 회의록 검색 (같은 프로젝트 우선)
        past_context = []
        if services.rag_service:
            try:
                past_context = await services.rag_service.retrieve_context(
                    user_id=current_user.id,
                    query_text=transcript[:2000],
                    project_name=transcript_record.project_name,
                )
                if past_context:
                    print(f"RAG: 과거 회의록 {len(past_context)}개 검색됨")
            except Exception as e:
                print(f"RAG 검색 실패 (무시): {e}")

        print(f"LLM ({gpt_model.value})로 회의록 작성 중...")
        start_time = time.time()
        result = await services.gpt_summarizer.summarize(
            transcript, model=gpt_model.value, context=context or None,
            past_context=past_context or None,
            glossary=glossary or None,
            project_memory=proj_memory,
            style_rules=style_rules or None,
        )
        gpt_time = time.time() - start_time

        summary = result["summary"]
        input_tokens = result["input_tokens"]
        output_tokens = result["output_tokens"]
        llm_cost = calculate_llm_cost(gpt_model.value, input_tokens, output_tokens)
        print(f"회의록 작성 완료! (소요 시간: {gpt_time:.2f}초, 비용: ${llm_cost:.6f})")

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
        if services.rag_service:
            try:
                metadata = {}
                if transcript_record.meeting_title:
                    metadata["meeting_title"] = transcript_record.meeting_title
                if transcript_record.project_name:
                    metadata["project_name"] = transcript_record.project_name
                await services.rag_service.embed_and_store(
                    user_id=current_user.id,
                    summary_id=summary_record.id,
                    summary_text=summary,
                    metadata=metadata,
                )
            except Exception as e:
                print(f"RAG 저장 실패 (무시): {e}")

        # 프로젝트 누적 메모리 갱신 (백그라운드 — 응답 지연 없음)
        if transcript_record.project_id:
            background_tasks.add_task(
                project_memory.run_memory_update,
                project_id=transcript_record.project_id,
                user_id=current_user.id,
                new_summary=summary,
                meeting_title=transcript_record.meeting_title,
                meeting_date=transcript_record.created_at.strftime("%Y-%m-%d") if transcript_record.created_at else None,
            )

        # 완료 자동 이메일 알림 (백그라운드, 실패 무시) — "수정하러 가기" 딥링크 포함
        email_title = transcript_record.meeting_title or transcript_record.filename
        background_tasks.add_task(
            send_summary_email_background,
            to_email=current_user.email,
            subject=f"[Summarying!] 회의록 완성 — {email_title}",
            summary_text=summary,
            summary_id=summary_record.id,
        )

        # 파일 저장 또는 응답 준비
        summary_path = os.path.join(OUTPUT_DIR, f"meeting_minutes_{timestamp}_{unique_id}.txt")
        summary_url = None

        if return_file or save_files:
            async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
                await f.write(summary)
            print(f"회의록 파일 생성: {summary_path}")
            summary_url = upload_file_to_s3(
                summary_path,
                f"summaries/meeting_minutes_{timestamp}_{unique_id}.txt",
                content_type="text/plain"
            )

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

        if return_file:
            return FileResponse(
                path=summary_path,
                media_type="text/plain",
                filename=f"meeting_minutes_{timestamp}.txt",
                headers={
                    "Content-Disposition": f'attachment; filename="meeting_minutes_{timestamp}.txt"'
                }
            )

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


# ============================================
# Transcript 레코드 조회
# ============================================

@router.get("/transcripts")
async def get_transcripts(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 모든 STT 변환 레코드 조회 (페이지네이션)"""
    records = crud.get_all_transcript_records(db, current_user.id, skip=skip, limit=limit)
    return {"success": True, "count": len(records), "records": records}


@router.get("/transcripts/{transcript_id}")
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


@router.get("/transcripts/{transcript_id}/summaries")
async def get_transcript_summaries(
    transcript_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 STT 레코드에 대한 모든 요약 조회 (소유권 확인)"""
    summaries = crud.get_summaries_by_transcript(db, transcript_id, current_user.id)
    return {"success": True, "count": len(summaries), "summaries": summaries}


# ============================================
# Summary 레코드 조회/편집/버전
# ============================================

@router.get("/summaries")
async def get_summaries(
    skip: int = 0,
    limit: int = 20,
    q: str = "",
    days: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자의 모든 요약 레코드 조회 (페이지네이션 + 검색 + 기간 필터).
    q 파라미터가 있으면 파일명/회의제목/프로젝트명/요약본문에서 검색한다.
    days 지정 시 최근 N일 내 생성분만 (처리 내역 피드용).
    total은 필터 조건에 맞는 전체 건수 (페이지네이션 UI용)."""
    if q and q.strip():
        records = crud.search_summary_records(db, current_user.id, q.strip(), skip=skip, limit=limit)
    else:
        records = crud.get_all_summary_records(db, current_user.id, skip=skip, limit=limit, days=days)
    total = crud.count_summary_records(db, current_user.id, keyword=q, days=None if (q and q.strip()) else days)
    return {
        "success": True,
        "count": len(records),
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": [serialize_summary_for_list(r) for r in records],
    }


@router.get("/summaries/{summary_id}")
async def get_summary(
    summary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 요약 레코드 조회 (소유권 확인). 처음 열람 시 읽음 처리된다."""
    record = crud.get_summary_record(db, summary_id, current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")
    crud.mark_summary_viewed(db, record)
    transcript = record.transcript
    return {
        "success": True,
        "record": {
            "id": record.id,
            "transcript_id": record.transcript_id,
            "summary": record.summary,
            "gpt_model": record.gpt_model,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "transcript": transcript.transcript if transcript else None,
            "filename": transcript.filename if transcript else None,
            "meeting_title": transcript.meeting_title if transcript else None,
            "project_id": transcript.project_id if transcript else None,
            "project_name": transcript.project_name if transcript else None,
        },
    }


@router.put("/summaries/{summary_id}/project")
async def update_summary_project(
    summary_id: int,
    body: SummaryProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회의록의 프로젝트 분류 변경 (소유권 확인). project_id=null이면 해제.

    과거 회의록을 나중에 프로젝트로 분류할 때 사용. 분류를 마친 뒤
    프로젝트 상세 > AI 메모리 탭의 '전체 재구축'을 누르면 메모리에 반영된다."""
    record = crud.set_summary_project(db, summary_id, current_user.id, body.project_id)
    if not record:
        raise HTTPException(status_code=404, detail="회의록 또는 프로젝트를 찾을 수 없습니다")

    transcript = record.transcript
    # RAG 메타데이터 동기화 (프로젝트 우선 검색이 새 분류를 따르도록)
    if services.rag_service:
        metadata = {}
        if transcript.meeting_title:
            metadata["meeting_title"] = transcript.meeting_title
        if transcript.project_name:
            metadata["project_name"] = transcript.project_name
        services.rag_service.update_summary_metadata(current_user.id, summary_id, metadata)

    return {
        "success": True,
        "summary_id": record.id,
        "project_id": transcript.project_id,
        "project_name": transcript.project_name,
    }


@router.put("/summaries/{summary_id}")
async def update_summary(
    summary_id: int,
    body: SummaryUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약 텍스트 편집 (소유권 확인). 변경 시 새 버전이 자동 누적된다.
    저장 후 백그라운드로 컨텍스트 자동 학습을 트리거한다."""
    # 변경 전 직전 버전 본문을 미리 잡아둔다 (학습 작업에 사용)
    pre_summary = None
    pre_record = crud.get_summary_record(db, summary_id, current_user.id)
    if pre_record:
        pre_summary = pre_record.summary

    record = crud.update_summary_text(db, summary_id, current_user.id, body.summary)
    if not record:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")

    version_count = len(record.versions) if record.versions is not None else 1

    # 실제로 내용이 바뀐 경우에만 학습 트리거
    if pre_summary is not None and pre_summary != record.summary:
        transcript_record = record.transcript
        background_tasks.add_task(
            context_learner.run_learning_task,
            summary_id=record.id,
            user_id=current_user.id,
            project_id=transcript_record.project_id if transcript_record else None,
            project_name=transcript_record.project_name if transcript_record else None,
            prev_content=pre_summary,
            curr_content=record.summary,
        )

    return {
        "success": True,
        "summary_id": record.id,
        "summary": record.summary,
        "version_count": version_count,
        "latest_version_no": version_count,
    }


@router.delete("/summaries/{summary_id}")
async def delete_summary(
    summary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약 레코드 삭제 (소유권 확인). 버전 이력과 RAG 임베딩도 함께 정리된다."""
    ok = crud.delete_summary_record(db, summary_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")

    # RAG 임베딩 동기 정리 (실패해도 무시 — 검색에 노이즈만 남음)
    if services.rag_service:
        services.rag_service.delete_summary(current_user.id, summary_id)

    return {"success": True}


@router.get("/summaries/{summary_id}/versions")
async def list_summary_versions(
    summary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """요약의 모든 버전 이력 조회 (소유권 확인)"""
    versions = crud.get_summary_versions(db, summary_id, current_user.id)
    if versions is None:
        raise HTTPException(status_code=404, detail="Summary 레코드를 찾을 수 없습니다")
    return {
        "success": True,
        "summary_id": summary_id,
        "count": len(versions),
        "versions": [
            {
                "version_no": v.version_no,
                "source": v.source,
                "content": v.content,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
    }


@router.get("/summaries/{summary_id}/versions/{version_no}")
async def get_summary_version(
    summary_id: int,
    version_no: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """특정 버전 단건 조회 (소유권 확인)"""
    version = crud.get_summary_version(db, summary_id, version_no, current_user.id)
    if not version:
        raise HTTPException(status_code=404, detail="해당 버전을 찾을 수 없습니다")
    return {
        "success": True,
        "summary_id": summary_id,
        "version": {
            "version_no": version.version_no,
            "source": version.source,
            "content": version.content,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        },
    }


@router.post("/summaries/{summary_id}/send-email")
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
        await send_summary_email(current_user.email, subject, record.summary, summary_id=record.id)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이메일 발송 실패: {e}")

    return {"success": True, "message": f"{current_user.email}로 이메일을 발송했습니다"}


# ============================================
# 검색
# ============================================

@router.get("/search/transcripts")
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


@router.get("/search/summaries")
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
