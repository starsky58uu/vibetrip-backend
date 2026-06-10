"""Spots 進階整合測試 — 排序、分頁、toggle 邊界。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import RegisterRequest
from app.schemas.spot import PersonalSpotCreateRequest, PersonalSpotUpdateRequest
from app.services import auth_service, spot_service

pytestmark = pytest.mark.integration


async def _user(db_session: AsyncSession):
    suffix = uuid4().hex[:8]
    req = RegisterRequest(
        username=f"ext{suffix}",
        email=f"ext{suffix}@example.com",
        password="secure-pass-123",
    )
    return (await auth_service.register_user(db_session, req)).user


@pytest.mark.asyncio
async def test_community_sorts_and_pagination(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    for i in range(3):
        await spot_service.create_personal_spot(
            db_session,
            user,
            PersonalSpotCreateRequest(
                latitude=25.033 + i * 0.001,
                longitude=121.565 + i * 0.001,
                note=f"spot-{i}",
                is_public=True,
            ),
        )

    popular = await spot_service.list_community_spots(db_session, user, sort="popular", limit=2)
    assert popular.pagination.has_more is True
    assert popular.pagination.next_cursor

    page2 = await spot_service.list_community_spots(
        db_session, user, sort="popular", limit=2, cursor=popular.pagination.next_cursor
    )
    assert len(page2.data) >= 1

    nearby = await spot_service.list_community_spots(
        db_session, user, sort="nearby", lat=25.033, lon=121.565, limit=2
    )
    assert len(nearby.data) >= 1
    if nearby.pagination.next_cursor:
        nearby2 = await spot_service.list_community_spots(
            db_session,
            user,
            sort="nearby",
            lat=25.033,
            lon=121.565,
            limit=2,
            cursor=nearby.pagination.next_cursor,
        )
        assert len(nearby2.data) >= 1

    recent = await spot_service.list_community_spots(db_session, None, sort="recent", limit=2)
    assert len(recent.data) >= 1
    if recent.pagination.next_cursor:
        recent2 = await spot_service.list_community_spots(
            db_session,
            None,
            sort="recent",
            limit=2,
            cursor=recent.pagination.next_cursor,
        )
        assert len(recent2.data) >= 1


@pytest.mark.asyncio
async def test_update_sync_community_and_toggle_idempotent(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    spot = await spot_service.create_personal_spot(
        db_session,
        user,
        PersonalSpotCreateRequest(
            latitude=25.033,
            longitude=121.565,
            note="sync",
            is_public=False,
        ),
    )
    await spot_service.update_personal_spot(
        db_session,
        user,
        spot.id,
        PersonalSpotUpdateRequest(is_public=True, note="公開"),
    )
    page = await spot_service.list_community_spots(db_session, user, sort="recent")
    community_id = next(s.id for s in page.data if s.content == "公開")

    await spot_service.toggle_like(db_session, user, community_id)
    again = await spot_service.toggle_like(db_session, user, community_id)
    assert again.is_liked is False

    await spot_service.toggle_save(db_session, user, community_id)
    unsave = await spot_service.toggle_save(db_session, user, community_id)
    assert unsave.is_saved is False

    await spot_service.update_personal_spot(
        db_session,
        user,
        spot.id,
        PersonalSpotUpdateRequest(is_public=False),
    )


@pytest.mark.asyncio
async def test_update_public_spot_syncs_existing_community(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    spot = await spot_service.create_personal_spot(
        db_session,
        user,
        PersonalSpotCreateRequest(
            latitude=25.035,
            longitude=121.567,
            note="v1",
            is_public=True,
        ),
    )
    await spot_service.update_personal_spot(
        db_session,
        user,
        spot.id,
        PersonalSpotUpdateRequest(note="v2", image_url="http://img"),
    )
