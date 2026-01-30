# Meeting Minutes Bot - 변경 이력

## 2026-01-30: 오늘 작업 요약

### 완료된 작업
1. **사용자 동선 간소화**
   - 리뷰 화면 제거, STT 완료 후 자동 요약 진행
   - 업로드 화면에 AI 모델 선택 추가 (Claude Sonnet 4.5 기본값)

2. **PostgreSQL DB 연결 확인**
   - Railway PostgreSQL 서비스 연결 완료
   - API를 통한 데이터 조회 방법 문서화

3. **로컬 개발 환경 설정**
   - Python 가상환경 설정 (`source venv/bin/activate`)
   - 환경변수 설정: `.env` 파일에 `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
   - 로컬 실행: `python api.py` → http://localhost:8000/app

4. **상용 배포 완료**
   - 커밋: `65e1d2b` - feat: 사용자 동선 간소화 - 자동 STT + 요약 처리
   - Railway 자동 배포 완료, 상용 환경 정상 동작 확인

### 트러블슈팅
- **브라우저 캐시 문제**: 상용 환경에서 `Cannot read properties of null` 오류 발생
- **해결**: 강력 새로고침 (Cmd+Shift+R)으로 캐시 무효화

---

## 2026-01-30: 사용자 동선 간소화

### 변경 내용
- **변경 전**: 음원 업로드 → STT 대기 → 리뷰 화면 → 요약 버튼 클릭 → 요약 대기 → 결과
- **변경 후**: 음원 업로드 → STT + 요약 자동 처리 → 결과

### 주요 수정사항

#### 1. 업로드 화면에 AI 모델 선택 추가
- Claude Sonnet 4.5 (기본값) - 일반적인 회의록 요약에 가장 적합
- GPT-5.1 - 세부 내용을 포함한 심층 요약

#### 2. 리뷰 화면 제거
- 중간 단계 없이 바로 결과 화면으로 이동
- 사용자 경험 개선 (클릭 수 감소)

#### 3. 자동 요약 처리
- STT 완료 후 자동으로 요약 진행
- 업로드 화면에서 선택한 모델로 처리

### 수정 파일
- `frontend/index.html`: 모델 선택 UI 추가, 리뷰 섹션 제거
- `frontend/js/app.js`: handleConvert/handleSummarize 로직 수정

---

## 2026-01-30: PostgreSQL 데이터베이스 연결

### 데이터베이스 설정
- **호스팅**: Railway PostgreSQL 서비스
- **연결 방식**: Railway 대시보드에서 PostgreSQL 서비스 추가 후 환경변수 참조

### 환경변수 설정 (Railway Variables)
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```
> Railway에서 PostgreSQL 서비스의 DATABASE_URL을 참조하는 방식

### 상용 데이터 조회 방법

#### 1. API를 통한 조회
```bash
# 모든 STT 기록 조회
curl -s https://meeting-bot.jonny.kim/transcripts | python3 -m json.tool

# 모든 요약 기록 조회
curl -s https://meeting-bot.jonny.kim/summaries | python3 -m json.tool

# 특정 STT 기록 조회
curl -s https://meeting-bot.jonny.kim/transcripts/1 | python3 -m json.tool

# 키워드 검색
curl -s "https://meeting-bot.jonny.kim/search/transcripts?keyword=회의" | python3 -m json.tool
```

#### 2. DB 클라이언트로 직접 연결
1. Railway 대시보드 → PostgreSQL 서비스 → **Connect** 탭
2. 연결 정보 확인:
   - Host, Port, User, Password, Database
3. TablePlus, DBeaver, pgAdmin 등에서 연결

#### 3. Railway 대시보드에서 조회
1. Railway 대시보드 → PostgreSQL 서비스 → **Data** 탭
2. 테이블 조회 및 쿼리 실행 가능

### 데이터베이스 스키마
```sql
-- STT 결과 테이블
CREATE TABLE transcript_records (
    id SERIAL PRIMARY KEY,
    filename VARCHAR,
    file_size INTEGER,
    audio_duration FLOAT,
    transcript TEXT,
    whisper_model VARCHAR,
    stt_processing_time FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 요약 결과 테이블 (1:N 관계)
CREATE TABLE summary_records (
    id SERIAL PRIMARY KEY,
    transcript_id INTEGER REFERENCES transcript_records(id) ON DELETE CASCADE,
    summary TEXT,
    gpt_model VARCHAR,
    gpt_processing_time FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

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
