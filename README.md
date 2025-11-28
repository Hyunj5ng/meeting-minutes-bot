# 회의록봇 (Meeting Minutes Bot)

음성 파일을 자동으로 텍스트로 변환하고, GPT를 사용하여 체계적인 회의록으로 정리해주는 프로그램입니다.

## 주요 기능

- **STT (Speech-to-Text)**: OpenAI Whisper 오픈소스 모델을 사용하여 음성을 텍스트로 변환
- **회의록 생성**: GPT API를 사용하여 변환된 텍스트를 구조화된 회의록으로 정리
- **자동 저장**: 원본 텍스트와 정리된 회의록을 자동으로 파일로 저장
- **REST API**: FastAPI 기반 웹 API 제공 (웹 클라이언트와 연동 가능)

## 설치 방법

### 1. Python 설치 확인
Python 3.8 이상이 필요합니다.

```bash
python --version
```

### 2. 프로젝트 클론 및 이동

```bash
cd meeting-minutes-bot
```

### 3. 필요한 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. OpenAI API 키 설정

1. [OpenAI 웹사이트](https://platform.openai.com/)에서 API 키 발급
2. `.env.example` 파일을 `.env`로 복사
3. `.env` 파일을 열어서 API 키 입력

```bash
cp .env.example .env
```

`.env` 파일 내용:
```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

## 빠른 시작 (로컬 실행)

### 1. 가상환경 생성 및 활성화 (권장)

```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (macOS/Linux)
source venv/bin/activate

# 가상환경 활성화 (Windows)
venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일을 열어서 OpenAI API 키 입력
# OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 4. API 서버 실행

```bash
python api.py
```

서버가 시작되면 브라우저에서 http://localhost:8000/docs 를 열어 테스트할 수 있습니다.

### 5. 서버 종료

터미널에서 `Ctrl+C`를 누르면 서버가 종료됩니다.

---

## 사용 방법

### 방법 1: API 서버 실행 (권장)

웹 인터페이스나 다른 애플리케이션과 연동하려면 API 서버를 실행하세요.

```bash
python api.py
```

또는

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

서버가 실행되면 다음 주소에서 API 문서를 확인할 수 있습니다:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

#### API 엔드포인트

**POST /transcribe** - 음성 파일을 회의록으로 변환

```bash
curl -X POST "http://localhost:8000/transcribe" \
  -F "file=@meeting.mp3" \
  -F "save_files=true"
```

**응답 예시:**
```json
{
  "success": true,
  "filename": "meeting.mp3",
  "transcript": "회의 내용 원본 텍스트...",
  "summary": "정리된 회의록...",
  "timestamp": "20250128_143022",
  "saved_files": {
    "transcript": "output/transcript_20250128_143022_a1b2c3d4.txt",
    "summary": "output/meeting_minutes_20250128_143022_a1b2c3d4.txt"
  }
}
```

**GET /health** - 서버 상태 확인

```bash
curl http://localhost:8000/health
```

**DELETE /cleanup?days=7** - 오래된 파일 정리

```bash
curl -X DELETE "http://localhost:8000/cleanup?days=7"
```

### 방법 2: CLI 사용 (기존 방식)

커맨드라인에서 직접 실행하려면:

```bash
python main.py <음성파일경로>
```

예시:
```bash
python main.py meeting.mp3
```

#### Whisper 모델 크기 선택

정확도와 속도를 조절할 수 있습니다:

```bash
python main.py meeting.mp3 small
```

**모델 옵션:**
- `tiny`: 가장 빠름, 낮은 정확도
- `base`: 균형잡힌 선택 (기본값, 권장)
- `small`: 더 정확하지만 느림
- `medium`: 높은 정확도, 매우 느림
- `large`: 최고 정확도, 가장 느림

### 지원하는 음성 파일 형식

- MP3
- WAV
- M4A
- OGG
- FLAC
- AAC

## 출력 결과

프로그램 실행 후 `output/` 폴더에 다음 파일들이 생성됩니다:

1. `transcript_YYYYMMDD_HHMMSS.txt`: STT로 변환된 원본 텍스트
2. `meeting_minutes_YYYYMMDD_HHMMSS.txt`: GPT로 정리된 회의록

회의록은 다음 형식으로 작성됩니다:
- 회의 주제
- 주요 논의 사항
- 결정 사항
- 액션 아이템
- 기타 사항

## 프로젝트 구조

```
meeting-minutes-bot/
├── main.py                 # CLI 실행 스크립트
├── api.py                  # FastAPI 웹 서버
├── stt_module.py          # Whisper STT 처리 모듈
├── gpt_summarizer.py      # GPT 요약 모듈
├── requirements.txt       # 필요한 패키지 목록
├── .env.example          # 환경변수 예시 파일
├── .gitignore            # Git 제외 파일 목록
├── README.md             # 프로젝트 설명서
├── uploads/              # 업로드 임시 파일 폴더 (자동 생성)
└── output/               # 결과 파일 저장 폴더 (자동 생성)
```

## 주의사항

- OpenAI API 사용 시 요금이 발생합니다 (GPT-4o-mini는 저렴한 편)
- 긴 오디오 파일은 처리 시간이 오래 걸릴 수 있습니다
- 처음 실행 시 Whisper 모델 다운로드로 시간이 소요될 수 있습니다

## GitHub에 코드 저장하기

### 1. GitHub에 새 리포지토리 생성

1. https://github.com 에서 로그인
2. 우측 상단 "+" 버튼 → "New repository" 클릭
3. 리포지토리 이름 입력 (예: `meeting-minutes-bot`)
4. Public 또는 Private 선택
5. **"Add a README file" 체크 해제** (이미 있음)
6. "Create repository" 클릭

### 2. 로컬 코드를 GitHub에 업로드

```bash
# Git 리포지토리 초기화 (아직 안했다면)
git init

# 파일 추가
git add .

# 커밋 생성
git commit -m "Initial commit: 회의록 봇 API"

# GitHub 리포지토리와 연결 (YOUR_USERNAME을 본인 GitHub 아이디로 변경)
git remote add origin https://github.com/YOUR_USERNAME/meeting-minutes-bot.git

# GitHub에 업로드
git push -u origin main
```

### 3. 다른 컴퓨터에서 사용하기

```bash
# 리포지토리 클론
git clone https://github.com/YOUR_USERNAME/meeting-minutes-bot.git
cd meeting-minutes-bot

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# .env 파일 생성 및 API 키 입력
cp .env.example .env
# .env 파일을 열어서 API 키 입력

# ffmpeg 설치 (macOS)
brew install ffmpeg

# 서버 실행
python api.py
```

## 문제 해결

### "OPENAI_API_KEY가 설정되지 않았습니다" 오류
- `.env` 파일이 올바른 위치에 있는지 확인
- API 키가 제대로 입력되었는지 확인

### Whisper 모델 로딩 실패
- 인터넷 연결 확인 (첫 실행 시 모델 다운로드 필요)
- 충분한 디스크 공간 확보

### ffmpeg 오류
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Windows**: https://ffmpeg.org/download.html 에서 다운로드

## 라이선스

MIT License
