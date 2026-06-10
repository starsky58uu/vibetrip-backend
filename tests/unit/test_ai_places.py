"""AI places 模組測試。"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.ai.places import (
    cached_text_search,
    dist_km,
    fetch_closing_times,
    filter_closing_soon,
    search_nearby,
    validate_closing_times,
)


def test_dist_km() -> None:
    d = dist_km(25.033, 121.565, 25.034, 121.566)
    assert 0 < d < 2


@pytest.mark.asyncio
async def test_cached_text_search_hit() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps([{"name": "A"}]))
    result = await cached_text_search(redis, "咖啡", 25.0, 121.0)
    assert result[0]["name"] == "A"


@pytest.mark.asyncio
async def test_cached_text_search_miss() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(return_value=[{"name": "B"}])
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        result = await cached_text_search(redis, "咖啡", 25.0, 121.0)
    assert result[0]["name"] == "B"


@pytest.mark.asyncio
async def test_cached_text_search_exception() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(side_effect=RuntimeError("api down"))
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        result = await cached_text_search(redis, "咖啡", 25.0, 121.0)
    assert result == []


@pytest.mark.asyncio
async def test_search_nearby_filters_and_supplements(monkeypatch) -> None:
    tw = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    monkeypatch.setattr("app.services.ai.places.datetime", type(datetime))
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

        places = [
            {
                "name": f"Shop{i}",
                "formatted_address": "addr",
                "rating": 4.0,
                "types": ["cafe"],
                "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
                "opening_hours": {"open_now": True},
                "place_id": f"p{i}",
            }
            for i in range(5)
        ]
        with (
            patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
            patch("app.services.ai.places.cached_text_search", AsyncMock(return_value=places)),
            patch("app.services.ai.places.random.sample", return_value=["咖啡廳"]),
        ):
            results = await search_nearby("cafe", 25.033, 121.565)
    assert len(results) >= 1
    assert "lat" in results[0]


def test_filter_closing_soon_keeps_24h() -> None:
    nearby = [{"name": "A", "closes_at": "24:00"}]
    assert filter_closing_soon(nearby, min_stay_min=30) == nearby


def test_filter_closing_soon_removes_soon() -> None:
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 21, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        nearby = [{"name": "A", "closes_at": "21:15"}]
        filtered = filter_closing_soon(nearby, min_stay_min=30)
    assert filtered == []


def test_validate_closing_times_drops_late_stay() -> None:
    nearby = [{"name": "Late Cafe", "closes_at": "21:00"}]
    items = [{"activity": "Late Cafe", "dur": "90min"}]
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        valid = validate_closing_times(items, nearby)
    assert valid == []


@pytest.mark.asyncio
async def test_fetch_closing_times_cached() -> None:
    place = {"place_id": "pid", "name": "Cafe"}
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"closes_at": "22:00"}))
    with patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)):
        await fetch_closing_times([place])
    assert place["closes_at"] == "22:00"


@pytest.mark.asyncio
async def test_fetch_closing_times_api() -> None:
    place = {"place_id": "pid", "name": "Cafe"}
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.place_details = AsyncMock(
        return_value={
            "opening_hours": {
                "periods": [
                    {
                        "open": {"day": (datetime.now(ZoneInfo("Asia/Taipei")).weekday() + 1) % 7},
                        "close": {"day": 0, "time": "2200"},
                    }
                ]
            }
        }
    )
    with (
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)),
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
    ):
        await fetch_closing_times([place])
    assert "closes_at" in place
