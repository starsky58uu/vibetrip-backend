"""nearby 分頁 cursor 整合測試。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import RegisterRequest
from app.schemas.spot import PersonalSpotCreateRequest
from app.services import auth_service, spot_service

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_nearby_pagination_with_cursor(db_session: AsyncSession) -> None:
    suffix = uuid4().hex[:8]
    user = (
        await auth_service.register_user(
            db_session,
            RegisterRequest(
                username=f"near{suffix}",
                email=f"near{suffix}@example.com",
                password="secure-pass-123",
            ),
        )
    ).user
    for i in range(4):
        await spot_service.create_personal_spot(
            db_session,
            user,
            PersonalSpotCreateRequest(
                latitude=25.033 + i * 0.0005,
                longitude=121.565 + i * 0.0005,
                note=f"n{i}",
                is_public=True,
            ),
        )
    page1 = await spot_service.list_community_spots(
        db_session, user, sort="nearby", lat=25.033, lon=121.565, limit=2
    )
    assert page1.pagination.has_more
    assert page1.pagination.next_cursor
    page2 = await spot_service.list_community_spots(
        db_session,
        user,
        sort="nearby",
        lat=25.033,
        lon=121.565,
        limit=2,
        cursor=page1.pagination.next_cursor,
    )
    assert len(page2.data) >= 1
