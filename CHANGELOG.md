# Meeting Minutes Bot - 변경 이력

## 2025-01-15: Railway 배포 완료

### 배포 정보
- **프로덕션 URL**: https://meeting-bot.jonny.kim/app
- **Railway 기본 URL**: https://meeting-minutes-bot-production.up.railway.app/app
- **API 문서**: https://meeting-bot.jonny.kim/docs
- **호스팅**: Railway (Docker 기반)

### 주요 변경사항

#### 1. Whisper API 변경
- 로컬 Whisper 모델 → OpenAI Whisper API로 변경
- 이유: Railway 빌드 타임아웃 (PyTorch + 모델 다운로드가 너무 오래 걸림)
- 파일: `stt_module.py`

#### 2. 프론트엔드 서빙
- FastAPI에서 정적 파일 직접 서빙
- `/app` 경로에서 프론트엔드 접근
- `/css`, `/js` 정적 파일 마운트
- 파일: `api.py`

#### 3. 데이터베이스
- SQLite 사용 (Railway 내부 파일시스템)
- 서버 시작 시 테이블 자동 생성 (`Base.metadata.create_all`)
- 주의: Railway 재배포 시 SQLite 데이터 초기화될 수 있음

### 환경변수 (Railway Variables)
```
OPENAI_API_KEY=sk-proj-xxx (필수)
```

### 프로젝트 구조
```
meeting-minutes-bot/
├── api.py              # FastAPI 메인 (프론트엔드 서빙 포함)
├── stt_module.py       # OpenAI Whisper API STT
├── gpt_summarizer.py   # GPT 요약
├── database.py         # SQLAlchemy 설정
├── models.py           # DB 모델 (TranscriptRecord, SummaryRecord)
├── crud.py             # DB CRUD 함수
├── frontend/
│   ├── index.html      # 메인 UI
│   ├── css/
│   └── js/app.js       # 프론트엔드 로직 (API_BASE_URL='')
├── Dockerfile          # Railway 배포용
├── railway.json        # Railway 설정
└── requirements.txt    # Python 의존성
```

### API 엔드포인트
| 경로 | 설명 |
|------|------|
| GET `/app` | 프론트엔드 UI |
| GET `/health` | 헬스체크 |
| GET `/docs` | Swagger API 문서 |
| POST `/transcribe-only` | STT만 수행 |
| POST `/summarize` | GPT 요약 |
| POST `/transcribe` | STT + 요약 한번에 |
| GET `/transcripts` | STT 기록 조회 |
| GET `/summaries` | 요약 기록 조회 |

### 다음 작업 시 참고사항
1. 코드 수정 후 `git push origin main` → Railway 자동 배포
2. 환경변수 변경은 Railway 대시보드에서 직접 수정
3. SQLite 대신 PostgreSQL 사용하려면 Railway에서 PostgreSQL 서비스 추가 후 `DATABASE_URL` 환경변수 설정

---

## 이전 커밋 히스토리
- `9e65eb0` fix: 서버 시작 시 데이터베이스 테이블 자동 생성
- `c77bf2f` feat: Railway에서 프론트엔드 함께 서빙
- `34d7bf1` refactor: 로컬 Whisper를 OpenAI Whisper API로 변경
- `d7973b7` feat: Railway 배포 설정 추가
- `42c2891` feat: Whisper API를 로컬 오픈소스 모델로 변경
