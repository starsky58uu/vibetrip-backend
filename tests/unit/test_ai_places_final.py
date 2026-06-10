"""ai/places 最後分支。"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.ai import places as ai_places


@pytest.mark.asyncio
async def test_search_hits_pool_limit_and_duplicate() -> None:
    tw = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    many = []
    for i in range(20):
        many.append(
            {
                "name": f"Shop{i}",
                "formatted_address": "a",
                "rating": 4.0,
                "types": ["cafe"],
                "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
                "opening_hours": {"open_now": True},
                "place_id": f"p{i}",
            }
        )
    dup = many[0].copy()
    dup["name"] = "Shop0"
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch("app.services.ai.places.cached_text_search", AsyncMock(return_value=many + [dup])),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert len(results) <= 15


@pytest.mark.asyncio
async def test_search_supplement_when_under_three() -> None:
    tw = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    one = {
        "name": "Only",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": True},
        "place_id": "p1",
    }
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch(
            "app.services.ai.places.cached_text_search", AsyncMock(side_effect=[[one], [one, one]])
        ),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert len(results) >= 1


def test_filter_closing_invalid_parse_kept() -> None:
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        kept = ai_places.filter_closing_soon([{"closes_at": "bad"}], 30)
    assert kept


@pytest.mark.asyncio
async def test_fetch_closing_invalid_time_length() -> None:
    places = [{"place_id": "pb", "name": "BadTime"}]
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    google_today = (datetime.now(ZoneInfo("Asia/Taipei")).weekday() + 1) % 7
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.place_details = AsyncMock(
        return_value={
            "opening_hours": {
                "periods": [
                    {
                        "open": {"day": google_today},
                        "close": {"day": google_today, "time": "99"},
                    }
                ]
            }
        }
    )
    with (
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)),
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
    ):
        await ai_places.fetch_closing_times(places)
    assert "closes_at" not in places[0]


@pytest.mark.asyncio
async def test_fetch_closing_skips_non_matching_day_and_bad_time() -> None:
    places = [{"place_id": "px", "name": "X"}]
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    google_today = (datetime.now(ZoneInfo("Asia/Taipei")).weekday() + 1) % 7
    other_day = (google_today + 1) % 7
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.place_details = AsyncMock(
        return_value={
            "opening_hours": {
                "periods": [
                    {
                        "open": {"day": other_day},
                        "close": {"day": other_day, "time": "99"},
                    }
                ]
            }
        }
    )
    with (
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)),
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
    ):
        await ai_places.fetch_closing_times(places)
    assert "closes_at" not in places[0]


@pytest.mark.asyncio
async def test_search_supplement_stops_at_fifteen() -> None:
    tw = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    seed = {
        "name": "Seed",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": True},
        "place_id": "p0",
    }
    supplement_batch = [
        {
            "name": f"Extra{i}",
            "formatted_address": "a",
            "rating": 4.0,
            "types": ["cafe"],
            "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
            "opening_hours": {"open_now": True},
            "place_id": f"e{i}",
        }
        for i in range(20)
    ]
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch(
            "app.services.ai.places.cached_text_search",
            AsyncMock(side_effect=[[seed], supplement_batch]),
        ),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert len(results) == 15


def test_validate_closing_parse_errors_and_drop() -> None:
    nearby = [{"name": "X", "closes_at": "bad"}]
    items = [{"activity": "X", "dur": "30min"}]
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        assert ai_places.validate_closing_times(items, nearby) == items

    nearby2 = [{"name": "Y", "closes_at": "20:30"}]
    items2 = [{"activity": "Y", "dur": "90min"}]
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        assert ai_places.validate_closing_times(items2, nearby2) == []


def test_validate_closing_early_morning_close() -> None:
    nearby = [{"name": "Dawn", "closes_at": "02:00"}]
    items = [{"activity": "Dawn", "dur": "180min"}]
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 23, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        assert ai_places.validate_closing_times(items, nearby) == []


def test_filter_closing_next_day_hours() -> None:
    with patch("app.services.ai.places.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 22, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        kept = ai_places.filter_closing_soon([{"closes_at": "01:00↑"}], min_stay_min=30)
    assert len(kept) == 1
