"""Refresh token rotation 單元測試。"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import create_token, decode_token_jti
from app.schemas.auth import RefreshRequest
from app.services import auth_service


@pytest.mark.asyncio
async def test_refresh_rotates_and_revokes_old() -> None:
    user_id = uuid4()
    old_jti = str(uuid4())
    old_refresh = create_token(user_id, token_type="refresh", jti=old_jti)

    stored: dict[str, str] = {old_jti: "1"}

    async def fake_exists(key: str) -> int:
        jti = key.split(":")[-1]
        return 1 if jti in stored else 0

    async def fake_delete(key: str) -> None:
        jti = key.split(":")[-1]
        stored.pop(jti, None)

    async def fake_set(key: str, value: str, ex: int) -> None:
        jti = key.split(":")[-1]
        stored[jti] = value

    mock_redis = AsyncMock()
    mock_redis.exists = fake_exists
    mock_redis.delete = fake_delete
    mock_redis.set = fake_set

    mock_user = AsyncMock()
    mock_user.id = user_id

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)

    with patch("app.services.auth_service.get_redis", AsyncMock(return_value=mock_redis)):
        resp = await auth_service.refresh_access_token(
            mock_db, RefreshRequest(refresh_token=old_refresh)
        )

    assert resp.access_token
    assert resp.refresh_token
    assert resp.refresh_token != old_refresh
    assert old_jti not in stored

    with patch("app.services.auth_service.get_redis", AsyncMock(return_value=mock_redis)):
        with pytest.raises(HTTPException) as exc:
            await auth_service.refresh_access_token(
                mock_db, RefreshRequest(refresh_token=old_refresh)
            )
    assert exc.value.status_code == 401


def test_access_token_has_jti() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    decoded_id, jti = decode_token_jti(token, expected_type="access")
    assert decoded_id == user_id
    assert jti
