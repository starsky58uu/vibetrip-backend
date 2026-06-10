"""盲盒 vibe 解析與 recommend 邏輯。"""

import random
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.trip import RecommendRequest
from app.services.trip_service import _resolve_vibe, get_trip, recommend


def _req(**kwargs) -> RecommendRequest:
    base = {"latitude": 25.033, "longitude": 121.565, "vibe_key": "walk"}
    base.update(kwargs)
    return RecommendRequest(**base)


def test_rainy_walk_becomes_rain() -> None:
    assert _resolve_vibe(_req(vibe_key="walk", weather_condition="Rain")) == "rain"


def test_rainy_photo_becomes_rain() -> None:
    assert _resolve_vibe(_req(vibe_key="photo", weather_condition="drizzle")) == "rain"


def test_clear_weather_keeps_walk() -> None:
    assert _resolve_vibe(_req(vibe_key="walk", weather_condition="Clear")) == "walk"


def test_random_picks_from_pool(monkeypatch) -> None:
    monkeypatch.setattr(random, "choice", lambda options: options[0])
    assert _resolve_vibe(_req(vibe_key="random")) == "cafe"


def test_thunderstorm_triggers_rain() -> None:
    assert _resolve_vibe(_req(vibe_key="walk", weather_condition="thunderstorm")) == "rain"


def test_explicit_vibe_passthrough() -> None:
    assert _resolve_vibe(_req(vibe_key="gift", weather_condition="Clear")) == "gift"


@pytest.mark.asyncio
async def test_recommend_ai_success() -> None:
    db = AsyncMock()
    ai = {
        "title": "AI 行程",
        "subtitle": "s",
        "items": [{"time": "12:00", "activity": "A", "desc": "d"}],
    }
    with patch("app.services.trip_service.generate_trip", AsyncMock(return_value=ai)):
        result = await recommend(db, _req())
    assert result.title == "AI 行程"
    assert result.vibe_key == "walk"


@pytest.mark.asyncio
async def test_recommend_falls_back_to_db() -> None:
    db = AsyncMock()
    template = MagicMock()
    template.id = uuid4()
    template.vibe_key = "walk"
    template.title = "DB 模板"
    template.items = []
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[template])))
        )
    )
    with patch(
        "app.services.trip_service.generate_trip", AsyncMock(side_effect=RuntimeError("AI down"))
    ):
        monkeypatch_random = patch("app.services.trip_service.random.choice", return_value=template)
        with monkeypatch_random:
            result = await recommend(db, _req())
    assert result.title == "DB 模板"


@pytest.mark.asyncio
async def test_recommend_db_not_found() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    with patch(
        "app.services.trip_service.generate_trip", AsyncMock(side_effect=RuntimeError("AI down"))
    ):
        with pytest.raises(HTTPException) as exc:
            await recommend(db, _req(vibe_key="gift"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_trip_not_found() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await get_trip(db, uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_trip_success() -> None:
    template = MagicMock()
    template.id = uuid4()
    template.vibe_key = "cafe"
    template.title = "T"
    template.items = []
    template.created_at = datetime.now(UTC)
    db = AsyncMock()
    db.get = AsyncMock(return_value=template)
    result = await get_trip(db, template.id)
    assert result.id == template.id
