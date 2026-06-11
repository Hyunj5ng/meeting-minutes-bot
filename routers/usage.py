"""
사용량/통계 조회 + 메타 정보 엔드포인트.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from core.config import DAILY_STT_LIMIT_MINUTES
from database import get_db
from gpt_summarizer import SYSTEM_PROMPT
from models import User

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 사용자의 사용량 현황 및 잔여 한도 반환"""
    daily_stt_minutes = crud.get_usage_minutes(db, current_user.id, "stt", "daily")
    monthly_stt_minutes = crud.get_usage_minutes(db, current_user.id, "stt", "monthly")
    monthly_cost = crud.get_usage_cost(db, current_user.id, "monthly")

    return {
        "stt": {
            "unit": "minutes",
            "daily": {"used": round(daily_stt_minutes, 1), "limit": DAILY_STT_LIMIT_MINUTES},
            "monthly": {"used": round(monthly_stt_minutes, 1), "limit": None},
        },
        "monthly_cost": round(monthly_cost, 4),
    }


@router.get("/me/stats")
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """내 페이지용 누적 사용 통계 (회의록 수, STT 분, 모델별 사용, 누적 비용)"""
    stats = crud.get_user_stats(db, current_user.id)
    stats["monthly_cost"] = round(crud.get_usage_cost(db, current_user.id, "monthly"), 4)
    return {"success": True, "stats": stats}


@router.get("/meta/system-prompt")
async def get_system_prompt(
    current_user: User = Depends(get_current_user),
):
    """회의록 생성에 사용되는 메타(시스템) 프롬프트 열람.

    실제 호출 시에는 여기에 회의 정보·프로젝트 메모리·글로서리·스타일 규칙·
    과거 회의록(RAG)이 추가로 주입된다."""
    return {
        "success": True,
        "system_prompt": SYSTEM_PROMPT,
        "injected_sections": [
            "회의 정보 (프로젝트/제목/참석자/키워드)",
            "프로젝트 누적 메모리 (결정사항·진행 주제·사람과 역할)",
            "알려진 표기/용어 글로서리 (내 컨텍스트 + 프로젝트 컨텍스트)",
            "사용자 스타일 선호 (수정 패턴에서 학습)",
            "참고 맥락 (과거 회의록 RAG 검색, 같은 프로젝트 우선)",
        ],
    }
