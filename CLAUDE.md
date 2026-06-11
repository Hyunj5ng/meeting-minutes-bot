# CLAUDE.md — Meeting Minutes Bot (Summarying!)

## 프로젝트 개요
AI 기반 회의 음성 파일 → 텍스트 변환(STT) → 회의록 요약 서비스.
브랜드명: **Summarying!**

## 기술 스택
- **Backend**: Python 3.11, FastAPI, Uvicorn
- **Frontend**: Vanilla HTML/CSS/JS (프레임워크 없음)
- **DB**: PostgreSQL (운영) / SQLite (로컬)
- **ORM**: SQLAlchemy + Alembic
- **배포**: Docker, Railway
- **외부 API**: Groq Whisper (STT), OpenAI GPT, Anthropic Claude

## 주요 파일
| 파일 | 역할 |
|------|------|
| `api.py` | FastAPI 엔트리포인트 — 앱 생성/정적 서빙만 (`api:app` 유지 필수) |
| `routers/` | 도메인별 엔드포인트 (auth / usage / transcription / summaries / projects / contexts) |
| `core/` | 공용 모듈 (config 상수, schemas, services 싱글톤, usage 한도, storage, serializers) |
| `stt_module.py` | Groq Whisper STT 처리 (청크 분할 포함) |
| `gpt_summarizer.py` | OpenAI/Claude LLM 요약 모듈 |
| `models.py` | SQLAlchemy ORM 모델 |
| `crud.py` | DB CRUD 연산 |
| `database.py` | DB 연결 설정 |
| `frontend/js/` | 클라이언트 UI — 역할별 모듈 9개. 전역 공유 방식이라 **로드 순서 중요** (core.js 처음, main.js 마지막 — index.html 참고) |
| `frontend/css/style.css` | 디자인 시스템 — `:root` 토큰 기반, 티일 단일 브랜드 컬러 |

## UI 디자인 원칙
- 단일 브랜드 컬러(티일 `--brand-600`) + 중립 배경. 상태 컬러(성공/경고/위험)는 의미가 있을 때만 사용
- 색/radius/그림자는 `style.css`의 `:root` 토큰만 사용 — 컴포넌트에 새 hex 값 직접 추가 금지
- 콤팩트 스티키 톱바(로고+네비+사용량+유저) 유지 — 큰 히어로 헤더로 되돌리지 않기

## 개발 명령어
```bash
source .venv/bin/activate   # 가상환경 활성화
pip install -r requirements.txt
python api.py               # 서버 실행 (http://localhost:8000/app)
```

## 코드 컨벤션
- 비동기 우선: 모든 I/O에 async/await 사용
- 한국어 STT 고정 (Whisper "ko" 파라미터)
- 커밋 메시지: 한국어, conventional commits 스타일 (feat/fix/chore 등)
- .env 파일 절대 커밋 금지

## 환경 변수 (필수)
- `GROQ_API_KEY` — STT용
- `OPENROUTER_API_KEY` — LLM 요약용 (OpenRouter 통합)
- `DATABASE_URL` — PostgreSQL (미설정 시 SQLite 사용)
- `RESEND_API_KEY` — 이메일 발송용 Resend API 키 (선택)
- `CHROMA_DATA_DIR` — ChromaDB 저장 경로 (기본: `chroma_data/`)
