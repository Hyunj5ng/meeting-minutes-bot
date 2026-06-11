"""
앱 전역 설정/상수 모음.

환경변수 기반 설정과 모델 가격표처럼 여러 라우터가 함께 쓰는 값은 전부 여기서 관리한다.
"""
import os

# 업로드 및 출력 디렉토리
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 허용 오디오 확장자 (프론트 fileInput accept와 동기화)
ALLOWED_AUDIO_EXTENSIONS = ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac']

# 합치기 모드에서 파트 간 구분자 (모델에게 "휴식 후 이어진 세션"임을 알림)
MERGE_PART_SEPARATOR = "\n\n---\n\n"

# 사용량 제한 (환경변수로 설정 가능) — STT 분(minutes) 단위, 일일 한도만 적용
DAILY_STT_LIMIT_MINUTES = int(os.getenv("DAILY_STT_LIMIT_MINUTES", "300"))

# 사용자별 동시 STT 작업 한도 (인메모리, 단일 워커 가정 — 멀티워커면 Redis로 교체 필요)
MAX_CONCURRENT_STT_PER_USER = int(os.getenv("MAX_CONCURRENT_STT_PER_USER", "3"))

# S3 (또는 호환 스토리지) 설정 — 미설정 시 업로드 스킵
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")

# API 모델별 가격표 (USD per 1M tokens, Whisper는 USD per minute)
MODEL_PRICING = {
    "whisper-large-v3-turbo": {"per_minute": 0.000667},
    # OpenAI
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    # Anthropic
    "claude-opus-4.6": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    # DeepSeek
    "deepseek-r1": {"input": 0.70, "output": 2.50},
    "deepseek-chat": {"input": 0.32, "output": 0.89},
    "deepseek-v3.2": {"input": 0.26, "output": 0.38},
    # Meta Llama
    "llama-3.3-70b": {"input": 2.75, "output": 2.75},
    "llama-4-maverick": {"input": 0.15, "output": 0.60},
    "llama-4-scout": {"input": 0.08, "output": 0.30},
}
