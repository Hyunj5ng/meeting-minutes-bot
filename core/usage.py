"""
비용 계산 + 사용량/동시성 제한.
"""
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy.orm import Session

import crud
from core.config import (
    DAILY_STT_LIMIT_MINUTES,
    MAX_CONCURRENT_STT_PER_USER,
    MODEL_PRICING,
)

_stt_active_counts: dict[int, int] = defaultdict(int)
_stt_counts_lock = asyncio.Lock()


@asynccontextmanager
async def acquire_stt_slot(user_id: int):
    """사용자별 동시 STT 슬롯 점유. 한도 초과 시 429 발생."""
    async with _stt_counts_lock:
        if _stt_active_counts[user_id] >= MAX_CONCURRENT_STT_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"동시에 처리할 수 있는 회의록은 최대 {MAX_CONCURRENT_STT_PER_USER}개입니다. 진행 중인 작업이 끝날 때까지 잠시 기다려주세요.",
            )
        _stt_active_counts[user_id] += 1
    try:
        yield
    finally:
        async with _stt_counts_lock:
            _stt_active_counts[user_id] -= 1
            if _stt_active_counts[user_id] <= 0:
                _stt_active_counts.pop(user_id, None)


def calculate_stt_cost(audio_duration_seconds: float) -> float:
    """STT 비용 계산 (USD). Groq Whisper는 분당 $0.000667"""
    if not audio_duration_seconds or audio_duration_seconds <= 0:
        return 0.0
    minutes = audio_duration_seconds / 60.0
    return round(minutes * MODEL_PRICING["whisper-large-v3-turbo"]["per_minute"], 6)


def calculate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """LLM 비용 계산 (USD). 토큰 수 × 모델별 단가"""
    pricing = MODEL_PRICING.get(model)
    if not pricing or "input" not in pricing:
        return 0.0
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return round(cost, 6)


def check_usage_limit(db: Session, user_id: int, audio_minutes: float = 0.0):
    """STT 사용량(분) 한도를 확인하고 초과 시 HTTPException(429)을 발생시킨다."""
    daily_used = crud.get_usage_minutes(db, user_id, "stt", period="daily")
    if daily_used + audio_minutes > DAILY_STT_LIMIT_MINUTES:
        remaining = max(0, DAILY_STT_LIMIT_MINUTES - daily_used)
        raise HTTPException(
            status_code=429,
            detail=f"일일 사용 한도({DAILY_STT_LIMIT_MINUTES}분)를 초과합니다. 잔여: {remaining:.0f}분. 내일 다시 시도해주세요."
        )
