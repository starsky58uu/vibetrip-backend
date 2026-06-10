"""Auth service 錯誤路徑測試。"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import create_token, hash_password
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.services import auth_service


@pytest.mark.asyncio
async def test_register_duplicate_user() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=object()))
    )
    req = RegisterRequest(
        username="dup",
        email="dup@example.com",
        password="pass12345",
        display_name="Dup",
    )
    with pytest.raises(HTTPException) as exc:
        await auth_service.register_user(db, req)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password() -> None:
    user = MagicMock()
    user.hashed_password = hash_password("right")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=user)))
    with pytest.raises(HTTPException) as exc:
        await auth_service.login_user(db, LoginRequest(username="u", password="wrong"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_user_not_found() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    with pytest.raises(HTTPException) as exc:
        await auth_service.login_user(db, LoginRequest(username="nope", password="x"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await auth_service.refresh_access_token(AsyncMock(), RefreshRequest(refresh_token="bad"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_inactive_jti() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="refresh")
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=0)
    with patch("app.services.auth_service.get_redis", AsyncMock(return_value=mock_redis)):
        with pytest.raises(HTTPException) as exc:
            await auth_service.refresh_access_token(
                AsyncMock(), RefreshRequest(refresh_token=token)
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_user_deleted() -> None:
    user_id = uuid4()
    jti = str(uuid4())
    token = create_token(user_id, token_type="refresh", jti=jti)
    mock_redis = AsyncMock()
    mock_redis.exists = AsyncMock(return_value=1)
    mock_redis.delete = AsyncMock()
    mock_redis.set = AsyncMock()
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with patch("app.services.auth_service.get_redis", AsyncMock(return_value=mock_redis)):
        with pytest.raises(HTTPException) as exc:
            await auth_service.refresh_access_token(db, RefreshRequest(refresh_token=token))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await auth_service.logout_user(RefreshRequest(refresh_token="bad"))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_token() -> None:
    user_id = uuid4()
    jti = str(uuid4())
    token = create_token(user_id, token_type="refresh", jti=jti)
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock()
    with patch("app.services.auth_service.get_redis", AsyncMock(return_value=mock_redis)):
        await auth_service.logout_user(RefreshRequest(refresh_token=token))
    mock_redis.delete.assert_awaited_once()
