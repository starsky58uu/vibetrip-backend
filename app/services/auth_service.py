"""認證服務層 — register / login / refresh。"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)


async def register_user(db: AsyncSession, req: RegisterRequest) -> TokenResponse:
    """註冊新帳號。"""

    # 檢查帳號 / email 是否已存在
    existing = await db.execute(
        select(User).where((User.username == req.username) | (User.email == req.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="帳號或信箱已被註冊",
        )

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return _build_token_response(user)


async def login_user(db: AsyncSession, req: LoginRequest) -> TokenResponse:
    """登入 — 驗證帳密後簽發 token。"""
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
        )

    return _build_token_response(user)


async def refresh_access_token(db: AsyncSession, req: RefreshRequest) -> AccessTokenResponse:
    """用 refresh_token 換新的 access_token。"""
    from jose import JWTError

    try:
        user_id = decode_token(req.refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 無效或已過期",
        )

    # 確認使用者還存在
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="使用者不存在")

    return AccessTokenResponse(
        access_token=create_token(user.id, token_type="access"),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _build_token_response(user: User) -> TokenResponse:
    """統一組 TokenResponse，register 和 login 共用。"""
    from app.schemas.user import UserResponse

    return TokenResponse(
        user=UserResponse.model_validate(user),
        access_token=create_token(user.id, token_type="access"),
        refresh_token=create_token(user.id, token_type="refresh"),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
