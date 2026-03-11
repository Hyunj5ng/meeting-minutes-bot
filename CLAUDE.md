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
| `api.py` | FastAPI 메인 서버 (엔드포인트 전체) |
| `stt_module.py` | Groq Whisper STT 처리 (청크 분할 포함) |
| `gpt_summarizer.py` | OpenAI/Claude LLM 요약 모듈 |
| `models.py` | SQLAlchemy ORM 모델 |
| `crud.py` | DB CRUD 연산 |
| `database.py` | DB 연결 설정 |
| `frontend/js/app.js` | 클라이언트 UI 로직 |
| `frontend/css/style.css` | 트로피칼 테마 스타일링 |

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
- `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` — LLM 요약용
- `DATABASE_URL` — PostgreSQL (미설정 시 SQLite 사용)
