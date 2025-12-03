"""
데이터베이스 연결 설정
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# 데이터베이스 URL (환경변수에서 가져오기, 없으면 SQLite 사용)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./meeting_minutes.db")

# PostgreSQL URL 형식 변경 (Heroku 등에서 postgres:// 사용 시)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLAlchemy 엔진 생성
if DATABASE_URL.startswith("sqlite"):
    # SQLite용 설정
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL용 설정
    engine = create_engine(DATABASE_URL)

# 세션 팩토리
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스
Base = declarative_base()


def get_db():
    """
    데이터베이스 세션 의존성
    FastAPI에서 사용
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
