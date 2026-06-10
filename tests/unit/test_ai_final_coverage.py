"""補齊 ai/places 與 enrichment 最後幾行。"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.ai import enrichment as ai_enrichment, places as ai_places


@pytest.mark.asyncio
async def test_enrich_far_place_rejected_and_transit_wait_invalid() -> None:
    items = [{"activity": "遠店", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(
        return_value=[{"geometry": {"location": {"lat": 30.0, "lng": 130.0}}}]
    )
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await ai_enrichment.enrich_distances(items, 25.033, 121.565, [])
    assert out[0].get("dist", "") == ""


@pytest.mark.asyncio
async def test_check_transit_missing_dep_time_and_long_wait() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    gmaps = AsyncMock()
    no_dep = {
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"value": 600},
                        "steps": [
                            {"travel_mode": "WALKING", "duration": {"value": 200}},
                            {"travel_mode": "TRANSIT", "transit_details": {"line": {}}},
                        ],
                    }
                ]
            }
        ]
    }
    long_wait = {
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"value": 600},
                        "steps": [
                            {"travel_mode": "WALKING", "duration": {"value": 200}},
                            {
                                "travel_mode": "TRANSIT",
                                "transit_details": {
                                    "departure_time": {"value": int(now.timestamp()) + 3600},
                                    "line": {"vehicle": {"type": "BUS"}, "name": "207"},
                                },
                            },
                        ],
                    }
                ]
            }
        ]
    }
    gmaps.directions = AsyncMock(side_effect=[no_dep, long_wait])
    with patch("app.services.ai.enrichment.datetime") as mock_dt:
        mock_dt.now.return_value = now
        assert await ai_enrichment.check_transit(gmaps, 25.0, 121.0, 25.01, 121.01) is None
        assert await ai_enrichment.check_transit(gmaps, 25.0, 121.0, 25.01, 121.01) is None


@pytest.mark.asyncio
async def test_search_early_morning_unknown_hours() -> None:
    tw = datetime(2026, 6, 10, 7, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    unknown_hours = {
        "name": "Shop",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["restaurant"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "place_id": "p",
    }
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch("app.services.ai.places.cached_text_search", AsyncMock(return_value=[unknown_hours])),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_enrich_assigns_coord_within_5km() -> None:
    items = [{"activity": "近店", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(
        return_value=[{"geometry": {"location": {"lat": 25.034, "lng": 121.566}}}]
    )
    mock_g.directions = AsyncMock(return_value={"routes": []})
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await ai_enrichment.enrich_distances(items, 25.033, 121.565, [])
    assert out[0]["dist"] == ""


@pytest.mark.asyncio
async def test_check_transit_directions_raises() -> None:
    gmaps = AsyncMock()
    gmaps.directions = AsyncMock(side_effect=RuntimeError("api"))
    assert await ai_enrichment.check_transit(gmaps, 1.0, 2.0, 3.0, 4.0) is None


def test_validate_closing_skip_empty_nearby_or_items() -> None:
    assert ai_places.validate_closing_times([], [{"name": "A"}]) == []
    assert ai_places.validate_closing_times([{"activity": "A"}], []) == [{"activity": "A"}]
