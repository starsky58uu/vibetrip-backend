"""Auth 整合測試 — register / login / refresh rotation。"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth_service

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_register_and_login_service(db_session: AsyncSession) -> None:
    suffix = uuid4().hex[:8]
    req = RegisterRequest(
        username=f"intuser{suffix}",
        email=f"int{suffix}@example.com",
        password="secure-pass-123",
        display_name="Integration",
    )
    tokens = await auth_service.register_user(db_session, req)
    assert tokens.access_token
    assert tokens.refresh_token

    login = await auth_service.login_user(
        db_session, LoginRequest(username=req.username, password=req.password)
    )
    assert login.user.username == req.username


@pytest.mark.asyncio
async def test_refresh_rotates_token(integration_client: AsyncClient) -> None:
    suffix = uuid4().hex[:8]
    reg = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "username": f"ref{suffix}",
            "email": f"ref{suffix}@example.com",
            "password": "secure-pass-123",
        },
    )
    assert reg.status_code == 201
    old_refresh = reg.json()["refresh_token"]

    refreshed = await integration_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["access_token"]
    assert body.get("refresh_token")
    assert body["refresh_token"] != old_refresh

    # 舊 refresh token 不可再用
    replay = await integration_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh(integration_client: AsyncClient) -> None:
    suffix = uuid4().hex[:8]
    reg = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "username": f"out{suffix}",
            "email": f"out{suffix}@example.com",
            "password": "secure-pass-123",
        },
    )
    refresh = reg.json()["refresh_token"]
    access = reg.json()["access_token"]

    logout = await integration_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout.status_code == 204

    again = await integration_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert again.status_code == 401
