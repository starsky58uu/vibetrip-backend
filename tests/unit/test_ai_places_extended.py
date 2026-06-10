"""ai/places 剩餘分支測試。"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.ai import places as ai_places


@pytest.mark.asyncio
async def test_search_nearby_night_tolerant_and_supplement_log() -> None:
    tw = datetime(2026, 6, 10, 23, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    open_none = {
        "name": "Bar",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["bar"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "place_id": "p1",
    }
    supplement = {
        "name": "Supp",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": True},
        "place_id": "p2",
    }
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch(
            "app.services.ai.places.cached_text_search",
            AsyncMock(side_effect=[[open_none], [supplement, supplement, supplement]]),
        ),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert len(results) >= 1


def test_validate_closing_times_keeps_valid_and_invalid_dur() -> None:
    nearby = [{"name": "Cafe", "closes_at": "23:00"}]
    items = [
        {"activity": "Cafe", "dur": "30min"},
        {"activity": "Cafe", "dur": "bad", "dur_raw": True},
    ]
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        valid = ai_places.validate_closing_times(items, nearby)
    assert len(valid) >= 1


@pytest.mark.asyncio
async def test_fetch_closing_24h_and_next_day() -> None:
    places = [{"place_id": "p24", "name": "24h"}, {"place_id": "pnd", "name": "late"}]
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    google_today = (datetime.now(ZoneInfo("Asia/Taipei")).weekday() + 1) % 7
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.place_details = AsyncMock(
        side_effect=[
            {"opening_hours": {"periods": [{"open": {"day": google_today}, "close": None}]}},
            {
                "opening_hours": {
                    "periods": [
                        {
                            "open": {"day": google_today},
                            "close": {"day": (google_today + 1) % 7, "time": "0100"},
                        }
                    ]
                }
            },
        ]
    )
    with (
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)),
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
    ):
        await ai_places.fetch_closing_times(places)
    assert places[0].get("closes_at") == "24:00"
    assert places[1].get("closes_at", "").endswith("↑")
