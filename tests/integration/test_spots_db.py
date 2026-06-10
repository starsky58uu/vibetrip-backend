"""Spots 整合測試 — PostGIS + 互動。"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import RegisterRequest
from app.schemas.spot import PersonalSpotCreateRequest
from app.services import auth_service, spot_service

pytestmark = pytest.mark.integration


async def _register(db_session: AsyncSession, suffix: str) -> tuple[str, str]:
    req = RegisterRequest(
        username=f"spot{suffix}",
        email=f"spot{suffix}@example.com",
        password="secure-pass-123",
        display_name="Spot User",
    )
    tokens = await auth_service.register_user(db_session, req)
    return tokens.access_token, tokens.user.id


@pytest.mark.asyncio
async def test_personal_spot_lifecycle(db_session: AsyncSession) -> None:
    suffix = uuid4().hex[:8]
    req = RegisterRequest(
        username=f"p{suffix}",
        email=f"p{suffix}@example.com",
        password="secure-pass-123",
    )
    tokens = await auth_service.register_user(db_session, req)
    user = tokens.user

    created = await spot_service.create_personal_spot(
        db_session,
        user,
        PersonalSpotCreateRequest(
            latitude=25.033,
            longitude=121.565,
            note="整合測試足跡",
            is_public=True,
        ),
    )
    assert created.note == "整合測試足跡"

    spots = await spot_service.list_personal_spots(db_session, user)
    assert any(s.id == created.id for s in spots)

    page = await spot_service.list_community_spots(db_session, user, sort="recent")
    community_id = next(s.id for s in page.data if s.content == "整合測試足跡")
    assert community_id is not None

    liked = await spot_service.toggle_like(db_session, user, community_id)
    assert liked.is_liked is True
    unliked = await spot_service.toggle_like(db_session, user, community_id)
    assert unliked.is_liked is False

    saved = await spot_service.toggle_save(db_session, user, community_id)
    assert saved.is_saved is True
    saved_list = await spot_service.list_saved_spots(db_session, user)
    assert any(s.id == community_id for s in saved_list)

    from app.schemas.spot import PersonalSpotUpdateRequest

    updated = await spot_service.update_personal_spot(
        db_session,
        user,
        created.id,
        PersonalSpotUpdateRequest(note="更新後", is_public=False),
    )
    assert updated.note == "更新後"

    await spot_service.delete_personal_spot(db_session, user, created.id)


@pytest.mark.asyncio
async def test_community_nearby_requires_coords(integration_client: AsyncClient) -> None:
    resp = await integration_client.get("/api/v1/spots/community", params={"sort": "nearby"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_spots_endpoints_http(
    integration_client: AsyncClient, db_session: AsyncSession
) -> None:
    suffix = uuid4().hex[:8]
    access, _user_id = await _register(db_session, suffix)
    headers = {"Authorization": f"Bearer {access}"}

    create = await integration_client.post(
        "/api/v1/spots/personal",
        headers=headers,
        json={"latitude": 25.034, "longitude": 121.566, "note": "http test", "is_public": True},
    )
    assert create.status_code == 201

    community = await integration_client.get("/api/v1/spots/community")
    assert community.status_code == 200
    community_id = community.json()["data"][0]["id"]

    me = await integration_client.get("/api/v1/spots/personal", headers=headers)
    assert me.status_code == 200

    like = await integration_client.post(
        f"/api/v1/spots/community/{community_id}/like", headers=headers
    )
    assert like.status_code == 200
