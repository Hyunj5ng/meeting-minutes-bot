"""
요청/응답 스키마와 선택지 Enum.
"""
from enum import Enum
from pydantic import BaseModel


class LLMModel(str, Enum):
    # OpenAI
    GPT_54_PRO = "gpt-5.4-pro"
    GPT_54 = "gpt-5.4"
    GPT_54_NANO = "gpt-5.4-nano"
    # Anthropic
    CLAUDE_OPUS_46 = "claude-opus-4.6"
    CLAUDE_SONNET_46 = "claude-sonnet-4.6"
    CLAUDE_HAIKU_45 = "claude-haiku-4.5"
    # Google
    GEMINI_25_PRO = "gemini-2.5-pro"
    GEMINI_25_FLASH = "gemini-2.5-flash"
    GEMINI_25_FLASH_LITE = "gemini-2.5-flash-lite"
    # DeepSeek
    DEEPSEEK_R1 = "deepseek-r1"
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_V32 = "deepseek-v3.2"
    # Meta Llama
    LLAMA_33_70B = "llama-3.3-70b"
    LLAMA_4_MAVERICK = "llama-4-maverick"
    LLAMA_4_SCOUT = "llama-4-scout"


class WhisperModel(str, Enum):
    """Whisper API는 단일 모델을 쓰므로 값은 기록용."""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class SummaryUpdateRequest(BaseModel):
    summary: str


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    memory: str | None = None  # AI 누적 메모리 직접 수정용


class ContextEntryCreateRequest(BaseModel):
    term: str
    correction: str
    note: str | None = None
    project_id: int | None = None  # None이면 개인 컨텍스트


class ContextEntryUpdateRequest(BaseModel):
    term: str | None = None
    correction: str | None = None
    note: str | None = None
