"""
사용량 조회 엔드포인트.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import crud
from auth import get_current_user
from core.config import DAILY_STT_LIMIT_MINUTES
from database import get_db
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
