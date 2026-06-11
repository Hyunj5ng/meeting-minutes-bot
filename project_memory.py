"""
프로젝트 누적 메모리 (rolling memory).

회의록이 생성될 때마다 백그라운드에서 LLM이 프로젝트의 누적 메모리를 갱신한다.
메모리는 다음 회의록 생성 시 프롬프트에 주입되어, 회의가 쌓일수록
프로젝트 맥락(결정사항·진행 주제·인물과 역할·용어)을 더 잘 기억하게 만든다.

흐름: /summarize 성공 → BackgroundTask(run_memory_update)
      → 기존 메모리 + 새 회의록 → 갱신된 메모리 → projects.memory 저장
"""
import os
from typing import Optional

import crud
from context_learner import _build_client
from database import SessionLocal

# 메모리 갱신에 사용할 모델 (작고 빠른 모델로 비용 최소화)
MEMORY_MODEL = os.getenv("PROJECT_MEMORY_MODEL", "google/gemini-2.5-flash")

# 메모리 본문 상한 (프롬프트 주입 비용 통제)
MAX_MEMORY_CHARS = 4000

# 새 회의록이 너무 길면 잘라서 전달
MAX_SUMMARY_INPUT_CHARS = 12000


MEMORY_SYSTEM_PROMPT = """당신은 한 프로젝트의 '누적 메모리'를 관리하는 비서입니다.

누적 메모리는 이 프로젝트의 다음 회의록을 작성할 AI에게 전달되는 압축된 장기 기억입니다.
입력으로 (1) 기존 메모리(없을 수 있음)와 (2) 방금 작성된 새 회의록이 주어집니다.
둘을 통합하여 갱신된 메모리 전체를 출력하세요.

형식 (마크다운, 이 구조를 유지):
## 프로젝트 개요
(1~2문장. 무엇을 만드는/하는 프로젝트인지)

## 핵심 결정사항
- (YYYY-MM-DD 또는 회의 차수) 결정 내용 — 배경 한 줄

## 진행 중인 주제
- 주제: 현재 상태, 다음 단계

## 사람과 역할
- 이름: 역할/담당 영역 (말버릇·관점 등 화자 구분에 도움되는 특징이 있으면 짧게)

## 용어·맥락
- 용어: 의미 (이 프로젝트에서만 통하는 표현)

규칙:
- 전체 {max_chars}자 이내. 넘치면 오래되었거나 해소된 항목부터 압축/삭제하세요.
- 해결/완료된 '진행 중인 주제'는 결정사항으로 옮기거나 제거하세요.
- 새 회의록의 정보가 기존 메모리와 충돌하면 새 정보를 우선하세요.
- 원문에 없는 내용을 지어내지 마세요.
- 메모리 본문만 출력하세요 (설명·코드펜스 금지)."""


async def _generate_updated_memory(
    old_memory: Optional[str],
    new_summary: str,
    project_name: str,
    meeting_title: Optional[str] = None,
    meeting_date: Optional[str] = None,
) -> Optional[str]:
    """LLM 호출로 갱신된 메모리 생성. 실패 시 None."""
    client = _build_client()
    if client is None:
        print("[ProjectMemory] OPENROUTER_API_KEY 미설정 — 메모리 갱신 스킵")
        return None

    meta_lines = [f"프로젝트명: {project_name}"]
    if meeting_title:
        meta_lines.append(f"이번 회의 제목: {meeting_title}")
    if meeting_date:
        meta_lines.append(f"이번 회의 일시: {meeting_date}")

    old_block = old_memory.strip() if old_memory and old_memory.strip() else "(아직 없음 — 첫 메모리를 작성하세요)"
    user_msg = f"""{chr(10).join(meta_lines)}

[기존 누적 메모리]
{old_block}

[새 회의록]
{new_summary[:MAX_SUMMARY_INPUT_CHARS]}

위 둘을 통합한 갱신된 누적 메모리를 출력하세요."""

    try:
        response = await client.chat.completions.create(
            model=MEMORY_MODEL,
            messages=[
                {"role": "system", "content": MEMORY_SYSTEM_PROMPT.format(max_chars=MAX_MEMORY_CHARS)},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        memory = (response.choices[0].message.content or "").strip()
        # 코드펜스로 감싸 오면 벗겨낸다
        if memory.startswith("```"):
            memory = memory.strip("`").lstrip("markdown").strip()
        if not memory:
            return None
        return memory[:MAX_MEMORY_CHARS]
    except Exception as e:
        print(f"[ProjectMemory] LLM 호출 실패: {e}")
        return None


async def run_full_rebuild(project_id: int, user_id: int) -> None:
    """프로젝트의 모든 회의록을 시간순으로 재생하며 메모리를 처음부터 다시 빌드.

    회의록을 나중에 프로젝트로 분류했거나, 메모리 기능 도입 전의 회의록이
    반영되지 않은 경우를 위한 수동 트리거 (POST /projects/{id}/rebuild-memory).
    BackgroundTask 진입점 — 실패는 로그만 남긴다."""
    try:
        db = SessionLocal()
        try:
            project = crud.get_project(db, project_id, user_id)
            if not project:
                return
            project_name = project.name
            summaries = crud.get_summaries_for_project_asc(db, user_id, project_id)
            inputs = [
                {
                    "summary": s.summary,
                    "title": s.transcript.meeting_title if s.transcript else None,
                    "date": s.created_at.strftime("%Y-%m-%d") if s.created_at else None,
                }
                for s in summaries
            ]
        finally:
            db.close()

        if not inputs:
            print(f"[ProjectMemory] project_id={project_id} 재구축 스킵 (회의록 없음)")
            return

        print(f"[ProjectMemory] project_id={project_id} 재구축 시작 ({len(inputs)}개 회의록, 시간순)")
        memory = None
        for i, item in enumerate(inputs, 1):
            updated = await _generate_updated_memory(
                old_memory=memory,
                new_summary=item["summary"],
                project_name=project_name,
                meeting_title=item["title"],
                meeting_date=item["date"],
            )
            if updated:
                memory = updated
            print(f"[ProjectMemory] 재구축 진행 {i}/{len(inputs)}")

        if not memory:
            print(f"[ProjectMemory] project_id={project_id} 재구축 실패 (메모리 생성 안 됨)")
            return

        db = SessionLocal()
        try:
            crud.set_project_memory(db, project_id, user_id, memory)
            print(f"[ProjectMemory] project_id={project_id} 재구축 완료 ({len(memory)}자)")
        finally:
            db.close()
    except Exception as e:
        print(f"[ProjectMemory] 재구축 실패 (무시): {e}")


async def run_memory_update(
    project_id: int,
    user_id: int,
    new_summary: str,
    meeting_title: Optional[str] = None,
    meeting_date: Optional[str] = None,
) -> None:
    """BackgroundTask 진입점. 실패는 로그만 남기고 조용히 종료한다."""
    try:
        db = SessionLocal()
        try:
            project = crud.get_project(db, project_id, user_id)
            if not project:
                return
            old_memory = project.memory
            project_name = project.name
        finally:
            db.close()

        updated = await _generate_updated_memory(
            old_memory=old_memory,
            new_summary=new_summary,
            project_name=project_name,
            meeting_title=meeting_title,
            meeting_date=meeting_date,
        )
        if not updated:
            return

        db = SessionLocal()
        try:
            crud.set_project_memory(db, project_id, user_id, updated)
            print(f"[ProjectMemory] project_id={project_id} 메모리 갱신 완료 ({len(updated)}자)")
        finally:
            db.close()
    except Exception as e:
        print(f"[ProjectMemory] 메모리 갱신 실패 (무시): {e}")
