"""AI enrichment 距離補全測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.enrichment import check_transit, enrich_distances, match_coord

NEARBY = [{"name": "公園", "lat": 25.034, "lon": 121.566}]


def test_match_coord_exact_and_partial() -> None:
    assert match_coord("公園", NEARBY) == (25.034, 121.566)
    assert match_coord("去公園走走", NEARBY) == (25.034, 121.566)
    assert match_coord("不存在", NEARBY) is None


def _walking_route(walk_min: int = 5, dist_m: int = 400) -> dict:
    return {
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"value": walk_min * 60},
                        "distance": {"value": dist_m},
                    }
                ]
            }
        ]
    }


def _transit_route(wait_offset: int = 600) -> dict:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_ts = int(datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")).timestamp())
    return {
        "routes": [
            {
                "legs": [
                    {
                        "duration": {"value": 900},
                        "steps": [
                            {"travel_mode": "WALKING", "duration": {"value": 300}},
                            {
                                "travel_mode": "TRANSIT",
                                "transit_details": {
                                    "departure_time": {"value": now_ts + wait_offset},
                                    "line": {
                                        "vehicle": {"type": "SUBWAY"},
                                        "short_name": "R",
                                    },
                                },
                            },
                        ],
                    }
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_enrich_distances_from_cache() -> None:
    items = [{"activity": "公園", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.directions = AsyncMock(return_value=_walking_route())
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await enrich_distances(items, 25.033, 121.565, NEARBY)
    assert "步行" in out[0]["dist"]


@pytest.mark.asyncio
async def test_enrich_distances_long_walk_uses_transit() -> None:
    items = [{"activity": "公園", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.directions = AsyncMock(side_effect=[_walking_route(walk_min=15), _transit_route()])
    with (
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
        patch("app.services.ai.enrichment.datetime") as mock_dt,
    ):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        mock_dt.now.return_value = datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        out = await enrich_distances(items, 25.033, 121.565, NEARBY)
    assert out[0].get("dist")


@pytest.mark.asyncio
async def test_enrich_distances_text_search_and_far_reject() -> None:
    items = [{"activity": "神秘店", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(
        return_value=[{"geometry": {"location": {"lat": 30.0, "lng": 130.0}}}]
    )
    mock_g.directions = AsyncMock(return_value=_walking_route())
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await enrich_distances(items, 25.033, 121.565, [])
    assert "dist" not in out[0] or out[0]["dist"] == ""


@pytest.mark.asyncio
async def test_check_transit_bus_label() -> None:
    gmaps = AsyncMock()
    gmaps.directions = AsyncMock(return_value=_transit_route(wait_offset=600))
    with patch("app.services.ai.enrichment.datetime") as mock_dt:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        mock_dt.now.return_value = datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        result = await check_transit(gmaps, 25.0, 121.0, 25.01, 121.01)
    assert result is not None
    assert "捷運" in result


@pytest.mark.asyncio
async def test_check_transit_no_routes() -> None:
    gmaps = AsyncMock()
    gmaps.directions = AsyncMock(return_value={"routes": []})
    assert await check_transit(gmaps, 1.0, 2.0, 3.0, 4.0) is None


@pytest.mark.asyncio
async def test_check_transit_walk_too_long() -> None:
    gmaps = AsyncMock()
    gmaps.directions = AsyncMock(
        return_value={
            "routes": [
                {
                    "legs": [
                        {
                            "duration": {"value": 3600},
                            "steps": [
                                {"travel_mode": "WALKING", "duration": {"value": 900}},
                                {
                                    "travel_mode": "TRANSIT",
                                    "transit_details": {"departure_time": {"value": 1}, "line": {}},
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    )
    assert await check_transit(gmaps, 1.0, 2.0, 3.0, 4.0) is None


@pytest.mark.asyncio
async def test_check_transit_bus_and_other_vehicle() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_ts = int(datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")).timestamp())
    gmaps = AsyncMock()

    bus_route = {
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
                                    "departure_time": {"value": now_ts + 300},
                                    "line": {"vehicle": {"type": "BUS"}, "name": "207"},
                                },
                            },
                        ],
                    }
                ]
            }
        ]
    }
    other_route = {
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
                                    "departure_time": {"value": now_ts + 300},
                                    "line": {"vehicle": {"type": "FERRY"}, "name": ""},
                                },
                            },
                        ],
                    }
                ]
            }
        ]
    }
    gmaps.directions = AsyncMock(side_effect=[bus_route, other_route])
    with patch("app.services.ai.enrichment.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        bus = await check_transit(gmaps, 25.0, 121.0, 25.01, 121.01)
        other = await check_transit(gmaps, 25.0, 121.0, 25.01, 121.01)
    assert bus and "公車" in bus
    assert other and "大眾運輸" in other
