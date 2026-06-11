"""
인증 엔드포인트 — Google 로그인 / 토큰 갱신 / 로그아웃 / 내 정보.
"""
from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session

import crud
from auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    revoke_refresh_token,
    verify_google_token,
    verify_refresh_token,
)
from database import get_db
from models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google")
async def google_login(
    token: str = Form(..., description="Google ID 토큰"),
    db: Session = Depends(get_db),
):
    """Google ID 토큰으로 로그인/회원가입 후 JWT 반환"""
    google_info = await verify_google_token(token)

    # 기존 사용자 조회 또는 신규 생성
    user = crud.get_user_by_google_id(db, google_info["google_id"])
    if user:
        user = crud.update_user_login(
            db, user,
            name=google_info["name"],
            picture=google_info["picture"],
        )
    else:
        user = crud.create_user(
            db,
            google_id=google_info["google_id"],
            email=google_info["email"],
            name=google_info["name"],
            picture=google_info["picture"],
        )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(db, user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        }
    }


@router.post("/refresh")
async def refresh_access_token(
    refresh_token: str = Form(..., description="리프레시 토큰"),
    db: Session = Depends(get_db),
):
    """리프레시 토큰으로 새 액세스 토큰 발급"""
    user = verify_refresh_token(db, refresh_token)
    new_access_token = create_access_token(user.id, user.email)
    return {"access_token": new_access_token}


@router.post("/logout")
async def logout_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """로그아웃 — 리프레시 토큰 무효화"""
    revoke_refresh_token(db, current_user)
    return {"message": "로그아웃 완료"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """현재 로그인한 사용자 정보 반환"""
    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "picture": current_user.picture,
        }
    }
