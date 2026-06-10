"""Transit service 非同步路徑測試。"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.transit_service import (
    _load_youbike_status,
    _parse_bus_eta,
    get_bus_eta,
    get_mrt_eta,
    nearest_bus_stops,
    nearest_mrt_stations,
    nearest_youbike,
)


def test_parse_bus_eta_remaining_branches() -> None:
    assert _parse_bus_eta({"StopStatus": 1, "EstimateTime": 30}, "r", "s").status == "no_service"
    assert _parse_bus_eta({"StopStatus": 2, "EstimateTime": 30}, "r", "s").status == "departure"
    assert _parse_bus_eta({"StopStatus": 0, "EstimateTime": None}, "r", "s").status == "no_service"
    assert _parse_bus_eta({"StopStatus": 4, "EstimateTime": 30}, "r", "s").status == "no_service"


@pytest.mark.asyncio
async def test_get_bus_eta_cache_hit() -> None:
    redis = AsyncMock()
    payload = {
        "route_name": "207",
        "stop_name": "站",
        "eta_seconds": 60,
        "plate_number": None,
        "status": "in_transit",
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }
    redis.get = AsyncMock(return_value=json.dumps(payload))
    result = await get_bus_eta(redis, "207", "站")
    assert result.eta_seconds == 60


@pytest.mark.asyncio
async def test_get_bus_eta_fetches_tdx() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    mock_tdx = AsyncMock()
    mock_tdx.__aenter__ = AsyncMock(return_value=mock_tdx)
    mock_tdx.__aexit__ = AsyncMock(return_value=None)
    mock_tdx.get_bus_eta = AsyncMock(return_value={"StopStatus": 0, "EstimateTime": 45})
    with patch("app.services.transit_service.TDXClient", return_value=mock_tdx):
        result = await get_bus_eta(redis, "207", "站")
    assert result.status == "approaching"


@pytest.mark.asyncio
async def test_get_mrt_eta_station_missing() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=None)))
    result = await get_mrt_eta(redis, db, "不存在")
    assert result.next_trains == []


@pytest.mark.asyncio
async def test_get_mrt_eta_success() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    row = MagicMock()
    row.tdx_station_id = "R10"
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=row)))
    mock_tdx = AsyncMock()
    mock_tdx.__aenter__ = AsyncMock(return_value=mock_tdx)
    mock_tdx.__aexit__ = AsyncMock(return_value=None)
    mock_tdx.get_mrt_eta = AsyncMock(return_value=[{"TripHeadSign": "南", "EstimateTime": 120}])
    with patch("app.services.transit_service.TDXClient", return_value=mock_tdx):
        result = await get_mrt_eta(redis, db, "市政府")
    assert len(result.next_trains) == 1


@pytest.mark.asyncio
async def test_load_youbike_status_cache() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(
        return_value=json.dumps({"S1": {"available_rent": 3, "available_return": 2}})
    )
    data = await _load_youbike_status(redis)
    assert data["S1"]["available_rent"] == 3


@pytest.mark.asyncio
async def test_nearest_youbike_filters_and_limits() -> None:
    redis = AsyncMock()
    db = AsyncMock()
    rows = [
        {
            "tdx_station_id": "S1",
            "name": "A",
            "lat": 25.0,
            "lon": 121.0,
            "bike_type": "YouBike2.0",
            "distance_m": 100.0,
        },
        {
            "tdx_station_id": "S2",
            "name": "B",
            "lat": 25.001,
            "lon": 121.001,
            "bike_type": "YouBike2.0",
            "distance_m": 200.0,
        },
    ]
    db.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
        )
    )
    with patch(
        "app.services.transit_service._load_youbike_status",
        AsyncMock(
            return_value={
                "S1": {"available_rent": 0, "available_return": 1},
                "S2": {"available_rent": 5, "available_return": 0},
            }
        ),
    ):
        rent = await nearest_youbike(redis, db, 25.0, 121.0, "rent", limit=1)
        ret = await nearest_youbike(redis, db, 25.0, 121.0, "return", limit=1)
    assert len(rent) == 1
    assert rent[0].station_id == "S2"
    assert ret[0].station_id == "S1"


@pytest.mark.asyncio
async def test_nearest_youbike_empty() -> None:
    redis = AsyncMock()
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )
    assert await nearest_youbike(redis, db, 25.0, 121.0, "rent") == []


@pytest.mark.asyncio
async def test_nearest_bus_and_mrt_stops() -> None:
    db = AsyncMock()
    row = {"name": "站", "lat": 25.0, "lon": 121.0, "distance_m": 50.0}
    db.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    bus = await nearest_bus_stops(db, 25.0, 121.0)
    mrt = await nearest_mrt_stations(db, 25.0, 121.0)
    assert bus[0]["name"] == "站"
    assert mrt[0]["name"] == "站"
