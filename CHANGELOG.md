# Meeting Minutes Bot - 변경 이력

## 2026-06-11 (2차): 학습 시스템 + UX 디테일 개선

### 쓸수록 똑똑해지는 학습 시스템 (시니어 엔지니어 설계)
1. **프로젝트 AI 메모리 (rolling memory)** — `project_memory.py`
   - 회의록 생성마다 백그라운드에서 LLM이 프로젝트별 누적 메모리 갱신 (핵심 결정사항/진행 주제/사람과 역할/용어)
   - 다음 회의록 생성 시 메모리가 프롬프트에 주입 → 회의가 쌓일수록 맥락·화자 파악력 향상
   - 프로젝트 상세에 "AI 메모리" 탭 — 열람 + 직접 수정 가능 (`PUT /projects/{id}`의 memory 필드)
   - DB: `projects.memory`, `projects.memory_updated_at` (마이그레이션 c3d8e91a7b42)
2. **스타일 학습** — context_learner 확장
   - 회의록 수정 diff에서 용어 교정 외에 구조/형식 선호("액션아이템은 표로" 등)를 추출해 다음 요약에 반영
   - DB: `context_entries.entry_type` ('term' | 'style'), 자동 학습 스타일 규칙 상한 20개
   - 내 컨텍스트/프로젝트 컨텍스트 화면에 "AI가 학습한 스타일 선호" 섹션 (삭제 가능)
3. **화자 귀속 강화** — 요약 프롬프트에 화자 추론 원칙 추가 (참석자·역할·발언 단서 기반, 불확실 시 "(추정)" 표기)
4. **RAG 개선** — 같은 프로젝트 회의록 우선 검색, 회의록 삭제 시 임베딩 동기 정리

### UX 디테일 개선 (시니어 디자이너 피드백 반영)
1. **토스트 알림 시스템** — 차단형 alert() 전면 교체 (완료/실패/이메일/저장/복사 등), 액션 버튼 지원
2. **작업 완료 시 자동 결과 표시** — 생성 화면에서 한가하면 바로 펼치고, 아니면 "결과 보기" 액션 토스트
3. **회의록 삭제** — `DELETE /summaries/{id}` + 대시보드 hover 삭제 버튼 (버전·임베딩까지 정리)
4. **대시보드 → 결과 동선** — 결과 카드에 "← 내 회의록" 백링크 (목록에서 열었을 때만)
5. **처리 중 이탈 경고** — 활성 작업 있을 때 beforeunload 확인
6. **파일 선택 후 드롭존 콤팩트화** — 거대한 드롭존이 "추가용" 한 줄로 축소
7. **모달 키보드** — Esc 닫기, 프로젝트명 Enter 저장

---

## 2026-06-11: UI 전면 리디자인 + 코드 구조 리팩토링

### UI 리디자인 (시니어 디자이너 피드백 반영)
1. **비주얼 아이덴티티 정리**
   - 4색 그라디언트 배경 + 무지개 카드 스트라이프 제거 → 중립 배경(`#F6F8F8`) + 티일 단일 브랜드 컬러
   - 포커스 링/액센트/진행바 전부 티일로 통일 (앰버 포커스 제거)
   - 상태 컬러(성공/경고/위험)는 작업 카드 상태, 자동 학습 항목 등 의미 있는 곳에만 사용
2. **헤더 콤팩트화**
   - 176px 로고 + 타이틀 + 서브타이틀 + 사용량 + 네비 (~화면 절반) → 56px 스티키 톱바 한 줄
   - 첫 화면에서 업로드 영역이 바로 보임
3. **디자인 토큰 시스템** — `:root` CSS 변수로 색/radius/그림자/포커스 정의, 타이포 스케일 정규화
4. **죽은 CSS 제거** — 레거시 스테퍼, 구 file-info, options-grid 등 미사용 스타일 정리

### 코드 구조 리팩토링 (시니어 개발자 피드백 반영)
1. **백엔드**: `api.py` 1,561줄 모놀리스 → `routers/` 6개 + `core/` 6개 모듈로 분리
   - `api.py`는 앱 생성/정적 서빙만 담당 (`api:app` 엔트리포인트 유지 → 배포 영향 없음)
   - 중복 제거: 파일 확장자 검증/프로젝트 매핑/임시 저장을 공용 헬퍼로 추출
   - 레거시 `/transcribe` 엔드포인트 삭제 (프론트 미사용, 120줄 중복)
   - `/cleanup`에 인증 추가 (기존엔 비인증 호출 가능했음)
2. **프론트엔드**: `app.js` 2,362줄 → 역할별 9개 모듈 (core/api/auth/upload/jobs/result/dashboard/projects/main)
   - 전역 공유 방식 유지 (빌드 도구 불필요), index.html 로드 순서로 의존성 관리
   - 미사용 변수 제거 (summaryHistory, transcriptData), 프로젝트 탭 클릭 시 결과 탭 상태가 깨지는 잠재 버그 수정
3. **캐시 버스팅 일반화** — 하드코딩된 파일명 치환 → 정규식으로 모든 로컬 css/js에 `?v=` 자동 적용

---

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
