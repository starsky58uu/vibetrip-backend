"""spot_service 單元測試（mock DB）。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.spot import PersonalSpotUpdateRequest
from app.services import spot_service
from app.services.spot_service import _cursor_datetime


def test_cursor_datetime_passthrough() -> None:
    now = datetime.now(UTC)
    assert _cursor_datetime(now) is now
    assert _cursor_datetime(now.isoformat()) == now


@pytest.mark.asyncio
async def test_update_personal_wrong_owner_fields() -> None:
    owner = MagicMock()
    owner.id = uuid4()
    other_id = uuid4()
    spot = MagicMock()
    spot.owner_id = other_id
    spot.id = uuid4()
    db = AsyncMock()
    db.get = AsyncMock(return_value=spot)
    with pytest.raises(HTTPException):
        await spot_service.update_personal_spot(
            db, owner, spot.id, PersonalSpotUpdateRequest(note="x")
        )


@pytest.mark.asyncio
async def test_toggle_like_idempotent_else_branch() -> None:
    user = MagicMock()
    user.id = uuid4()
    spot_id = uuid4()
    community = MagicMock()
    community.likes_count = 3
    db = AsyncMock()
    db.get = AsyncMock(return_value=community)

    inserted = MagicMock(rowcount=0)
    deleted = MagicMock(rowcount=0)
    db.execute = AsyncMock(side_effect=[inserted, deleted])

    result = await spot_service.toggle_like(db, user, spot_id)
    assert result.is_liked is False
    assert result.likes_count == 3


@pytest.mark.asyncio
async def test_toggle_save_not_found() -> None:
    user = MagicMock()
    user.id = uuid4()
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException):
        await spot_service.toggle_save(db, user, uuid4())


@pytest.mark.asyncio
async def test_toggle_save_idempotent_else_branch() -> None:
    user = MagicMock()
    user.id = uuid4()
    spot_id = uuid4()
    community = MagicMock()
    community.saves_count = 2
    db = AsyncMock()
    db.get = AsyncMock(return_value=community)

    inserted = MagicMock(rowcount=0)
    deleted = MagicMock(rowcount=0)
    db.execute = AsyncMock(side_effect=[inserted, deleted])

    result = await spot_service.toggle_save(db, user, spot_id)
    assert result.is_saved is False
    assert result.saves_count == 2
