"""認證服務層 — register / login / refresh / logout。"""

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import build_key, get_redis
from app.core.security import (
    create_token,
    decode_token_jti,
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


def _refresh_ttl_seconds() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


async def _store_refresh_token(user_id: UUID, jti: str) -> None:
    redis = await get_redis()
    key = build_key("auth", "refresh", str(user_id), jti)
    await redis.set(key, "1", ex=_refresh_ttl_seconds())


async def _revoke_refresh_token(user_id: UUID, jti: str) -> None:
    redis = await get_redis()
    key = build_key("auth", "refresh", str(user_id), jti)
    await redis.delete(key)


async def _is_refresh_active(user_id: UUID, jti: str) -> bool:
    redis = await get_redis()
    key = build_key("auth", "refresh", str(user_id), jti)
    return bool(await redis.exists(key))


async def register_user(db: AsyncSession, req: RegisterRequest) -> TokenResponse:
    """註冊新帳號。"""

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

    return await _build_token_response(user)


async def login_user(db: AsyncSession, req: LoginRequest) -> TokenResponse:
    """登入 — 驗證帳密後簽發 token。"""
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
        )

    return await _build_token_response(user)


async def refresh_access_token(db: AsyncSession, req: RefreshRequest) -> AccessTokenResponse:
    """用 refresh_token 換新的 access_token（並 rotation refresh_token）。"""
    try:
        user_id, jti = decode_token_jti(req.refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 無效或已過期",
        ) from None

    if not await _is_refresh_active(user_id, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 已失效",
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="使用者不存在")

    await _revoke_refresh_token(user_id, jti)
    new_jti = str(uuid4())
    new_refresh = create_token(user.id, token_type="refresh", jti=new_jti)
    await _store_refresh_token(user.id, new_jti)

    return AccessTokenResponse(
        access_token=create_token(user.id, token_type="access"),
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def logout_user(req: RefreshRequest) -> None:
    """撤銷 refresh token。"""
    try:
        user_id, jti = decode_token_jti(req.refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 無效或已過期",
        ) from None

    await _revoke_refresh_token(user_id, jti)


async def _build_token_response(user: User) -> TokenResponse:
    """統一組 TokenResponse，register 和 login 共用。"""
    from app.schemas.user import UserResponse

    refresh_jti = str(uuid4())
    refresh_token = create_token(user.id, token_type="refresh", jti=refresh_jti)
    await _store_refresh_token(user.id, refresh_jti)

    return TokenResponse(
        user=UserResponse.model_validate(user),
        access_token=create_token(user.id, token_type="access"),
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
