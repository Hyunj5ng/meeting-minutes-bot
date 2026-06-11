"""
FastAPI 엔트리포인트 — 앱 생성/미들웨어/정적 서빙만 담당한다.

엔드포인트 본문은 routers/ 패키지에, 공용 설정·헬퍼는 core/ 패키지에 있다.
    routers/auth.py           /auth/*
    routers/usage.py          /usage
    routers/transcription.py  /transcribe-only, /transcribe-merge, /cleanup
    routers/summaries.py      /summarize, /summaries*, /transcripts*, /search/*
    routers/projects.py       /projects*, /me/recent-attendees
    routers/contexts.py       /contexts*
"""
import asyncio
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

from core import services
from routers import auth as auth_router
from routers import contexts, projects, summaries, transcription, usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행되는 이벤트"""
    services.init_services()
    # 백그라운드에서 미임베딩 요약 백필 실행
    asyncio.create_task(services.backfill_embeddings())
    yield
    print("서버 종료 중...")


app = FastAPI(
    title="회의록 봇 API",
    description="음성 파일을 업로드하면 자동으로 회의록을 생성합니다",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정 (웹에서 접근 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(usage.router)
app.include_router(transcription.router)
app.include_router(summaries.router)
app.include_router(projects.router)
app.include_router(contexts.router)


@app.get("/")
async def root():
    """API 상태 확인"""
    return {
        "status": "running",
        "message": "회의록 봇 API가 정상 작동 중입니다",
        "endpoints": {
            "GET /app": "웹 프론트엔드",
            "GET /health": "서버 상태 확인",
        }
    }


@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "models_loaded": {
            "stt": services.stt_processor is not None,
            "gpt": services.gpt_summarizer is not None
        }
    }


# ============================================
# 프론트엔드 정적 파일 서빙
# ============================================

# 배포(재시작) 시마다 캐시 버스팅용 버전 생성
_CACHE_VERSION = str(int(time.time()))

app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")
app.mount("/images", StaticFiles(directory="frontend/images"), name="images")


@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    """프론트엔드 메인 페이지 서빙 (캐시 버스팅 + Google Client ID 주입)"""
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # 로컬 CSS/JS 참조 전부에 버전 쿼리스트링을 붙여 배포 시 캐시 자동 무효화
    html = re.sub(
        r'((?:href="css/|src="js/)[^"?]+)"',
        rf'\1?v={_CACHE_VERSION}"',
        html,
    )
    # Google Client ID 주입
    html = html.replace('__GOOGLE_CLIENT_ID__', os.getenv("GOOGLE_CLIENT_ID", ""))
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
