"""
컨텍스트 자동 학습 모듈.

사용자가 AI 회의록을 수정하면 이전/이후 버전의 diff를 LLM에 보내
인명/용어 교정을 추출하여 ContextEntry로 자동 적재한다.

- 개인(personal) 컨텍스트: 사람 이름 표기 등 사용자 전역으로 유효한 교정
- 프로젝트(project) 컨텍스트: 해당 프로젝트에서만 통하는 약어/용어
"""
import os
import json
import re
import difflib
from typing import List, Optional

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

import crud
from database import SessionLocal


# 자동 추출에 사용할 모델 (작고 빠른 모델로 비용 최소화)
EXTRACTION_MODEL = os.getenv("CONTEXT_EXTRACTION_MODEL", "google/gemini-2.5-flash-lite")

# 너무 큰 diff는 자르기 (토큰 제한 + 노이즈 방지)
MAX_DIFF_CHARS = 6000


EXTRACTION_SYSTEM_PROMPT = """당신은 회의록의 사용자 수정 내역을 분석하여 재사용 가능한 표기/용어 교정을 추출하는 분석가입니다.

입력: AI가 만든 회의록(이전 버전)과 사용자가 직접 고친 회의록(현재 버전)의 라인 단위 diff.

작업: 사용자가 어떤 부분을 어떻게 고쳤는지 보고, 다음 패턴 중 하나에 해당하는 교정만 추출하라.

추출할 패턴:
1. 인명/고유명사 표기 교정 — STT가 사람 이름을 잘못 인식하여 사용자가 바로잡은 경우.
   예) "강현정" → "강현종", "최운봐" → "최훈배"
   scope: personal (사용자의 모든 회의에서 유효)

2. 프로젝트 한정 용어/약어 정의 — 특정 프로젝트 맥락에서만 통하는 용어.
   예) "Y H" → "Yield Hub", "PDP" → "Product Detail Page"
   scope: project (해당 프로젝트의 회의에서만 적용)

3. 회사/팀 고유명사 — 일반적 표기로 통일 가능한 조직명/제품명.
   scope: personal

추출하지 말아야 할 것:
- 단순 어순 변경, 문장 다듬기, 마크다운 구조 변경
- 회의에서 한 번만 등장하는 일회성 정보
- 회의록 섹션 추가/삭제
- 문법 교정

반환 형식: 아래 JSON 배열만 출력 (다른 설명 금지).
[
  {"scope": "personal" | "project", "term": "잘못된 표기 (이전)", "correction": "올바른 표기 (이후)", "note": "선택적 짧은 설명"}
]

확실하지 않으면 추출하지 마라. 빈 배열 []도 정상 응답이다."""


def _build_diff_block(prev_content: str, curr_content: str) -> str:
    """라인 단위 unified diff 생성. 너무 길면 잘라낸다."""
    prev_lines = (prev_content or "").splitlines()
    curr_lines = (curr_content or "").splitlines()
    diff = difflib.unified_diff(
        prev_lines,
        curr_lines,
        fromfile="before",
        tofile="after",
        lineterm="",
        n=2,  # context 라인 수
    )
    text = "\n".join(diff)
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + "\n... (diff truncated)"
    return text


def _build_client() -> Optional[AsyncOpenAI]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://meeting-bot.jonny.kim",
            "X-Title": "Summarying-ContextLearner",
        },
    )


def _parse_json_array(raw: str) -> List[dict]:
    """LLM 응답에서 JSON 배열 파싱. 코드펜스/잡설 허용."""
    if not raw:
        return []
    # 마크다운 코드펜스 제거
    raw = raw.strip()
    if raw.startswith("```"):
        # ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if match:
            raw = match.group(1).strip()
    # 첫 번째 [ ... ] 추출
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        return []


async def extract_corrections(
    prev_content: str,
    curr_content: str,
    project_name: Optional[str] = None,
) -> List[dict]:
    """LLM을 호출하여 diff에서 교정 항목 추출.
    반환값: [{scope, term, correction, note}, ...]
    실패하면 빈 리스트."""
    if not prev_content or not curr_content or prev_content == curr_content:
        return []

    client = _build_client()
    if client is None:
        print("[ContextLearner] OPENROUTER_API_KEY 미설정 — 자동 학습 스킵")
        return []

    diff_text = _build_diff_block(prev_content, curr_content)
    if not diff_text.strip():
        return []

    project_hint = f"\n프로젝트명: {project_name}" if project_name else ""
    user_msg = f"""아래는 사용자가 AI 회의록을 수정한 diff입니다.{project_hint}

diff:
```
{diff_text}
```

위 diff에서 재사용 가능한 표기/용어 교정만 추출하여 JSON 배열로 반환하세요. 추출할 게 없으면 [] 만 출력하세요."""

    try:
        response = await client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        print(f"[ContextLearner] LLM 호출 실패: {e}")
        return []

    items = _parse_json_array(raw)
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        scope = item.get("scope")
        term = (item.get("term") or "").strip()
        correction = (item.get("correction") or "").strip()
        note = (item.get("note") or "").strip() or None
        if scope not in ("personal", "project"):
            continue
        if not term or not correction or term == correction:
            continue
        # 너무 길거나 너무 짧은 항목 필터
        if len(term) > 100 or len(correction) > 300:
            continue
        cleaned.append({
            "scope": scope,
            "term": term,
            "correction": correction,
            "note": note,
        })
    return cleaned


def _persist_entries(
    db: Session,
    user_id: int,
    project_id: Optional[int],
    items: List[dict],
) -> int:
    """추출 결과를 ContextEntry로 업서트. 적재된 건수 반환."""
    created = 0
    for item in items:
        scope = item["scope"]
        target_project_id = project_id if scope == "project" else None
        # 프로젝트 컨텍스트인데 transcript에 project_id가 없으면 → personal로 적재
        if scope == "project" and target_project_id is None:
            target_project_id = None  # 결국 personal로 들어감
        entry = crud.upsert_auto_context_entry(
            db,
            user_id=user_id,
            project_id=target_project_id,
            term=item["term"],
            correction=item["correction"],
            note=item.get("note"),
        )
        if entry is not None:
            created += 1
    return created


async def run_learning_task(
    summary_id: int,
    user_id: int,
    project_id: Optional[int],
    project_name: Optional[str],
    prev_content: str,
    curr_content: str,
) -> None:
    """BackgroundTask에서 실행되는 메인 진입점.
    실패는 silently 로그만 남기고 종료한다."""
    try:
        items = await extract_corrections(prev_content, curr_content, project_name)
        if not items:
            return
        print(f"[ContextLearner] summary_id={summary_id} 추출 {len(items)}건")
        db = SessionLocal()
        try:
            created = _persist_entries(db, user_id, project_id, items)
            print(f"[ContextLearner] summary_id={summary_id} 적재 완료 {created}건")
        finally:
            db.close()
    except Exception as e:
        print(f"[ContextLearner] 학습 작업 실패 (무시): {e}")
