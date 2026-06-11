# 회의록봇 (Meeting Minutes Bot)

음성 파일을 자동으로 텍스트로 변환하고, LLM을 사용하여 체계적인 회의록으로 정리해주는 웹 애플리케이션입니다.

## 주요 기능

- **STT (Speech-to-Text)**: Groq Whisper Large v3 Turbo API로 음성을 텍스트로 변환 (빠르고 저렴한 클라우드 STT)
- **회의록 생성**: OpenAI GPT 또는 Anthropic Claude를 선택하여 구조화된 회의록 작성
- **비용 추적**: 매 요청마다 STT/LLM 비용을 자동 계산하여 DB에 기록
- **동시 처리**: 비동기 아키텍처 + 멀티 워커로 최대 50명 동시 사용 지원
- **대용량 파일**: 25MB 초과 오디오 파일 자동 분할 처리
- **웹 프론트엔드**: 내장 웹 UI로 브라우저에서 바로 사용
- **REST API**: FastAPI 기반 웹 API 제공 (외부 연동 가능)
- **DB 저장**: PostgreSQL(또는 SQLite)에 변환 이력 및 비용 자동 저장

## 기술 스택

| 구분 | 기술 |
|------|------|
| STT | Groq Whisper Large v3 Turbo (`$0.000667/분`) |
| LLM | OpenAI GPT (5-mini, 5, 5.1, 4.1) / Anthropic Claude (Sonnet 4.5, Haiku 4.5) |
| 백엔드 | FastAPI + uvicorn (4 workers) |
| DB | PostgreSQL (프로덕션) / SQLite (로컬 개발) |
| 비동기 | AsyncGroq, AsyncOpenAI, AsyncAnthropic, aiofiles |
| 오디오 처리 | ffmpeg (분할/인코딩) |
| 파일 스토리지 | S3/R2 호환 (선택) |
| 배포 | Docker + Railway |

## 아키텍처

```
브라우저    ┌─ 워커1 ─┐
(50명)  ──▶│ 워커2  │──await(비동기)──▶ Groq Whisper / OpenAI / Claude API
           │ 워커3  │
           └─ 워커4 ─┘
                │
                ▼
           PostgreSQL (커넥션 풀 50개)
```

- 4개의 uvicorn 워커가 요청을 분산 처리
- 비동기 API 호출로 한 요청이 다른 요청을 차단하지 않음
- DB 커넥션 풀 (pool_size=20, max_overflow=30)로 동시 50개 연결 지원

## 설치 방법

### 1. Python 설치 확인
Python 3.8 이상이 필요합니다.

```bash
python --version
```

### 2. 프로젝트 클론 및 이동

```bash
git clone https://github.com/YOUR_USERNAME/meeting-minutes-bot.git
cd meeting-minutes-bot
```

### 3. 필요한 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. API 키 설정

`.env.example` 파일을 `.env`로 복사하고 API 키를 입력합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:
```
# 필수
GROQ_API_KEY=your_groq_api_key_here

# LLM (사용할 모델에 따라 하나 이상 설정)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# 선택: 외부 DB 연결 (없으면 SQLite 사용)
# DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME

# 선택: S3 또는 호환 스토리지(R2 등)
# S3_BUCKET_NAME=your-bucket
# S3_REGION=ap-northeast-2
# S3_ENDPOINT_URL=https://<custom-endpoint>
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
```

API 키 발급처:
- Groq: https://console.groq.com/
- OpenAI: https://platform.openai.com/
- Anthropic: https://console.anthropic.com/

## 빠른 시작 (로컬 실행)

### 1. 가상환경 생성 및 활성화 (권장)

```bash
python -m venv venv

# macOS/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어서 API 키 입력
```

### 4. API 서버 실행

```bash
python api.py
```

서버가 시작되면 브라우저에서 다음 주소로 접속합니다:
- 웹 UI: http://localhost:8000/app
- API 문서: http://localhost:8000/docs

---

## 사용 방법

### 방법 1: 웹 UI (권장)

서버 실행 후 http://localhost:8000/app 에서 바로 사용할 수 있습니다.

1. 음성 파일 업로드 (mp3, wav, m4a, ogg, flac, aac)
2. LLM 모델 선택 (GPT-5-mini, Claude Sonnet 등)
3. 회의록 자동 생성 및 다운로드

### 방법 2: API 직접 호출

#### 1단계: STT (음성 → 텍스트)

**POST /transcribe-only**

```bash
curl -X POST "http://localhost:8000/transcribe-only" \
  -F "file=@meeting.mp3" \
  -F "audio_duration=300" \
  -F "file_size=5000000"
```

응답:
```json
{
  "success": true,
  "transcript_id": 1,
  "filename": "meeting.mp3",
  "transcript": "변환된 텍스트...",
  "timestamp": "20250128_143022"
}
```

#### 2단계: 요약 (텍스트 → 회의록)

**POST /summarize**

```bash
curl -X POST "http://localhost:8000/summarize" \
  -F "transcript_id=1" \
  -F "gpt_model=gpt-5-mini"
```

응답:
```json
{
  "success": true,
  "summary_id": 1,
  "transcript_id": 1,
  "summary": "정리된 회의록...",
  "timestamp": "20250128_143045"
}
```

#### 기타 엔드포인트

| 엔드포인트 | 설명 |
|------------|------|
| `GET /health` | 서버 상태 확인 |
| `GET /transcripts` | STT 레코드 목록 조회 |
| `GET /transcripts/{id}` | 특정 STT 레코드 조회 |
| `GET /transcripts/{id}/summaries` | 특정 STT의 요약 목록 |
| `GET /summaries` | 요약 레코드 목록 조회 |
| `GET /search/transcripts?keyword=` | STT 레코드 검색 |
| `GET /search/summaries?keyword=` | 요약 레코드 검색 |
| `DELETE /cleanup?days=7` | 오래된 파일 정리 |

### 방법 3: CLI 사용

```bash
python main.py <음성파일경로>
```

### 지원하는 음성 파일 형식

MP3, WAV, M4A, OGG, FLAC, AAC

## 사용 가능한 LLM 모델

| 모델 | 특징 | 입력 비용 (1M 토큰) | 출력 비용 (1M 토큰) |
|------|------|---------------------|---------------------|
| `gpt-5-mini` | 빠르고 비용 효율적 (기본값) | $0.25 | $2.00 |
| `gpt-5-nano` | 최저 비용, 짧은 회의용 | $0.05 | $0.40 |
| `gpt-5` | 고품질 추론 | $1.25 | $10.00 |
| `gpt-5.1` | 최신 추론형 | $1.25 | $10.00 |
| `gpt-4.1` | 일반형, 가벼운 요약용 | $2.00 | $8.00 |
| `claude-sonnet-4-5` | 고품질, 빠른 속도 | $3.00 | $15.00 |
| `claude-haiku-4-5` | 가장 빠르고 경제적 | $1.00 | $5.00 |

## 비용 추적

모든 API 호출 비용이 DB에 자동 기록됩니다.

- **STT 비용**: Groq Whisper `$0.000667/분` (오디오 길이 기준)
- **LLM 비용**: 모델별 토큰 단가 × 사용 토큰 수

### 비용 확인 스크립트

```bash
DATABASE_URL="postgresql://..." python check_costs.py
```

출력 예시:
```
===== 비용 요약 =====
총 레코드: 15건
STT 비용 합계: $0.045
LLM 비용 합계: $0.032
총 비용: $0.077
건당 평균: $0.005
```

## 컨테이너 배포 (Railway/Render/Fly/Cloud Run 등)

### 환경 변수 설정 (필수)

| 변수 | 설명 | 필수 |
|------|------|------|
| `GROQ_API_KEY` | Groq API 키 (STT) | O |
| `OPENAI_API_KEY` | OpenAI API 키 (GPT 모델 사용 시) | 선택 |
| `ANTHROPIC_API_KEY` | Anthropic API 키 (Claude 모델 사용 시) | 선택 |
| `DATABASE_URL` | PostgreSQL URL | O (프로덕션) |
| `S3_BUCKET_NAME` | S3/R2 버킷명 | 선택 |

### Docker 빌드 및 실행

```bash
# 이미지 빌드
docker build -t meeting-minutes-bot .

# 컨테이너 실행 (로컬 확인)
docker run -p 8000:8000 \
  -e GROQ_API_KEY=$GROQ_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e DATABASE_URL=$DATABASE_URL \
  meeting-minutes-bot
```

이후 http://localhost:8000/app 으로 접속해 확인합니다.

### 호스팅 배포

Dockerfile 기반 배포를 지원하는 서비스(Railway/Render/Fly/Cloud Run)에 환경 변수를 설정하고 빌드/배포합니다.
프로덕션 환경에서는 4개의 uvicorn 워커가 자동으로 실행됩니다.

## 프로젝트 구조

```
meeting-minutes-bot/
├── api.py                  # FastAPI 엔트리포인트 (앱 생성, 정적 서빙)
├── core/                   # 공용 설정/헬퍼
│   ├── config.py           # 환경변수, 가격표, 한도 등 상수
│   ├── schemas.py          # Pydantic 요청 모델 + Enum
│   ├── services.py         # STT/LLM/RAG 클라이언트 싱글톤
│   ├── usage.py            # 비용 계산 + 사용량/동시성 제한
│   ├── storage.py          # 업로드 임시 저장 + S3 업로드
│   └── serializers.py      # 응답 직렬화 헬퍼
├── routers/                # 엔드포인트 (도메인별)
│   ├── auth.py             # /auth/*
│   ├── usage.py            # /usage
│   ├── transcription.py    # /transcribe-only, /transcribe-merge, /cleanup
│   ├── summaries.py        # /summarize, /summaries*, /transcripts*, /search/*
│   ├── projects.py         # /projects*, /me/recent-attendees
│   └── contexts.py         # /contexts*
├── stt_module.py           # Groq Whisper STT 처리 (비동기)
├── gpt_summarizer.py       # LLM 요약 모듈 (OpenAI/Claude, 비동기)
├── rag_service.py          # 과거 회의록 임베딩 검색 (ChromaDB)
├── context_learner.py      # 회의록 수정 → 컨텍스트 자동 학습
├── email_service.py        # Resend 이메일 발송
├── auth.py                 # JWT/Google 토큰 검증 헬퍼
├── database.py             # DB 연결 설정 (커넥션 풀)
├── models.py               # SQLAlchemy 데이터 모델
├── crud.py                 # DB CRUD 함수
├── alembic/                # DB 마이그레이션
├── check_costs.py          # 비용 확인 스크립트
├── requirements.txt        # Python 패키지 목록
├── Dockerfile              # 컨테이너 빌드 설정
├── frontend/               # 웹 프론트엔드 (Vanilla JS)
│   ├── index.html          # 메인 페이지
│   ├── css/style.css       # 디자인 시스템 + 스타일
│   └── js/                 # 역할별 모듈 (전역 공유, 로드 순서 중요)
│       ├── core.js         # 상수/전역 상태/유틸
│       ├── api.js          # authFetch + 사용량
│       ├── auth.js         # Google 로그인/토큰
│       ├── upload.js       # 파일 선택/참석자 자동완성
│       ├── jobs.js         # 작업 큐 (동시 3개)
│       ├── result.js       # 결과/버전/diff/편집
│       ├── dashboard.js    # 내 회의록 목록
│       ├── projects.js     # 프로젝트 + 컨텍스트
│       └── main.js         # 뷰 전환 + 초기화
├── uploads/                # 업로드 임시 파일 (자동 생성)
└── output/                 # 결과 파일 저장 (자동 생성)
```

## 주의사항

- Groq, OpenAI, Anthropic API 사용 시 각각 요금이 발생합니다
- 기본 LLM 모델은 `gpt-5-mini`이며, 웹 UI에서 모델 변경 가능
- 25MB 초과 오디오 파일은 자동으로 10분 단위로 분할 처리됩니다
- ffmpeg가 설치되어 있어야 합니다 (Docker 이미지에는 포함)

## 문제 해결

### API 키 관련 오류
- `.env` 파일이 프로젝트 루트에 있는지 확인
- 사용하려는 모델에 해당하는 API 키가 설정되어 있는지 확인
- Groq 키는 STT에 필수, OpenAI/Anthropic 키는 선택한 LLM 모델에 따라 필요

### ffmpeg 오류
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Windows**: https://ffmpeg.org/download.html 에서 다운로드
- **Docker**: Dockerfile에 이미 포함되어 있음

### DB 연결 오류
- `DATABASE_URL` 환경변수가 올바른 PostgreSQL URL인지 확인
- 설정하지 않으면 로컬 SQLite (`meeting_minutes.db`)를 자동 사용

## 라이선스

MIT License
