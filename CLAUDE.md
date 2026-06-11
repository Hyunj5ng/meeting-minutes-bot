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
| `gpt_summarizer.py` | OpenAI/Claude LLM 요약 모듈 (프로젝트 메모리·글로서리·스타일 규칙 주입) |
| `project_memory.py` | 프로젝트 누적 메모리 — 회의록 생성마다 백그라운드 LLM 갱신 |
| `context_learner.py` | 회의록 수정 diff → 용어 교정('term') + 스타일 선호('style') 자동 학습 |
| `rag_service.py` | 과거 회의록 임베딩 검색 (같은 프로젝트 우선, ChromaDB) |
| `models.py` | SQLAlchemy ORM 모델 |
| `crud.py` | DB CRUD 연산 |
| `database.py` | DB 연결 설정 |
| `frontend/js/` | 클라이언트 UI — 역할별 모듈 9개. 전역 공유 방식이라 **로드 순서 중요** (core.js 처음, main.js 마지막 — index.html 참고) |
| `frontend/css/style.css` | 디자인 시스템 — `:root` 토큰 기반, 티일 단일 브랜드 컬러 |

## 학습 시스템 (쓸수록 똑똑해지는 구조)
- **프로젝트 메모리**: `/summarize` 성공 → BackgroundTask로 `project_memory.run_memory_update` → `projects.memory` 갱신 → 다음 요약 프롬프트에 주입
- **메모리 전체 재구축**: `POST /projects/{id}/rebuild-memory` → 모든 회의록 시간순 재생 (과거 회의록을 나중에 분류한 경우)
- **수정 학습**: `PUT /summaries/{id}` → `context_learner.run_learning_task` → diff에서 용어('term')/스타일('style') 추출 → `context_entries`에 source='auto'로 적재
- 사용자가 직접 수정한(manual) 엔트리는 자동 학습이 절대 덮어쓰지 않음
- UI 알림은 alert() 금지 — `showToast()` (core.js) 사용

## UI 페이지 구조 (한 화면에 몰지 않기)
- 업로드(새 회의록) / 처리 중(작업 큐) / 내 회의록(리스트, 페이지네이션+읽지않음 점) / 상세·편집(detailView) / 프로젝트 / 내 컨텍스트 / 내 페이지(통계+메타 프롬프트)
- 생성 완료 시 결과를 바로 띄우지 않음 — 리스트에 unread로 쌓이고 사용자가 열어서 검토·수정 (`viewed_at` 마킹)
- 회의록 상세에서 프로젝트 분류 변경 가능 (`PUT /summaries/{id}/project`)

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
