"""Auth 端點測試。"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.auth import AccessTokenResponse, TokenResponse
from app.schemas.user import UserResponse


@pytest.mark.asyncio
async def test_register_endpoint(client) -> None:
    from datetime import UTC, datetime

    tokens = TokenResponse(
        user=UserResponse(
            id=uuid4(),
            username="u",
            email="u@e.com",
            display_name="U",
            avatar_url=None,
            created_at=datetime.now(UTC),
        ),
        access_token="a",
        refresh_token="r",
        expires_in=3600,
    )
    with patch(
        "app.api.v1.endpoints.auth.auth_service.register_user", AsyncMock(return_value=tokens)
    ):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"username": "testuser", "email": "u@e.com", "password": "pass12345"},
        )
    assert resp.status_code == 201
    assert resp.json()["access_token"] == "a"


@pytest.mark.asyncio
async def test_login_endpoint(client) -> None:
    with patch(
        "app.api.v1.endpoints.auth.auth_service.login_user",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="bad")),
    ):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "wrong"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_endpoint(client) -> None:
    body = AccessTokenResponse(access_token="new", refresh_token="newr", expires_in=3600)
    with patch(
        "app.api.v1.endpoints.auth.auth_service.refresh_access_token", AsyncMock(return_value=body)
    ):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "r"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_logout_endpoint(client) -> None:
    with patch("app.api.v1.endpoints.auth.auth_service.logout_user", AsyncMock()):
        resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "r"})
    assert resp.status_code == 204
