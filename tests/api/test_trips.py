"""Trips 端點測試。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.trip import TripPlanResponse


@pytest.mark.asyncio
async def test_recommend_trip(client) -> None:
    plan = TripPlanResponse(
        id=uuid4(),
        vibe_key="walk",
        title="T",
        subtitle="",
        items=[],
        generated_at=datetime.now(UTC),
    )
    with patch("app.api.v1.endpoints.trips.trip_service.recommend", AsyncMock(return_value=plan)):
        resp = await client.post(
            "/api/v1/trips/recommend",
            json={"latitude": 25.033, "longitude": 121.565, "vibe_key": "walk"},
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == "T"


@pytest.mark.asyncio
async def test_clear_trip_cache_forbidden_when_not_debug(authed_client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEBUG", False)
    resp = await authed_client.delete("/api/v1/trips/cache")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_clear_trip_cache_success(authed_client, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEBUG", True)
    mock_redis = AsyncMock()
    with (
        patch("app.api.v1.endpoints.trips.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.api.v1.endpoints.trips.scan_delete_pattern", AsyncMock(return_value=3)),
    ):
        resp = await authed_client.delete("/api/v1/trips/cache")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 3
