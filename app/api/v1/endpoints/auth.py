"""認證端點 — register / login / refresh。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """註冊新帳號，註冊成功直接拿到 token (免二次登入)。"""
    return await auth_service.register_user(db, req)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """登入，回傳 access_token + refresh_token。"""
    return await auth_service.login_user(db, req)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    req: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    """用 refresh_token 換新的 access_token。"""
    return await auth_service.refresh_access_token(db, req)
