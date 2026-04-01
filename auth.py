"""
인증 모듈 — Google OAuth 토큰 검증 및 JWT / Refresh Token 발급
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from jose import jwt, JWTError

from database import get_db
from models import User

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRATION_MINUTES = 60
REFRESH_TOKEN_EXPIRATION_DAYS = 30


async def verify_google_token(token: str) -> dict:
    """Google ID 토큰을 검증하고 사용자 정보를 반환한다."""
    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
        return {
            "google_id": idinfo["sub"],
            "email": idinfo.get("email", ""),
            "name": idinfo.get("name", ""),
            "picture": idinfo.get("picture", ""),
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Google 토큰 검증 실패: {e}")


def create_access_token(user_id: int, email: str) -> str:
    """JWT 액세스 토큰을 생성한다."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRATION_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(db: Session, user: User) -> str:
    """리프레시 토큰을 생성하고 DB에 저장한다."""
    token = uuid.uuid4().hex
    user.refresh_token = token
    user.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRATION_DAYS)
    db.commit()
    return token


def verify_refresh_token(db: Session, token: str) -> User:
    """리프레시 토큰을 검증하고 해당 사용자를 반환한다."""
    user = db.query(User).filter(User.refresh_token == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 리프레시 토큰입니다")
    if user.refresh_token_expires_at < datetime.now(timezone.utc):
        # 만료된 토큰 정리
        user.refresh_token = None
        user.refresh_token_expires_at = None
        db.commit()
        raise HTTPException(status_code=401, detail="리프레시 토큰이 만료되었습니다")
    return user


def revoke_refresh_token(db: Session, user: User):
    """리프레시 토큰을 무효화한다."""
    user.refresh_token = None
    user.refresh_token_expires_at = None
    db.commit()


async def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Authorization 헤더에서 JWT를 추출하고, 해당 사용자를 반환한다."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return user
