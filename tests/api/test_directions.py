"""Directions 端點測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.transit import DirectionsRequest, RouteOption, YoubikeStationResponse


@pytest.mark.asyncio
async def test_raw_directions(client) -> None:
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.directions = AsyncMock(return_value={"routes": [{"legs": []}, {"legs": []}]})
    with patch("app.api.v1.endpoints.directions.GoogleMapsClient", return_value=mock_g):
        resp = await client.get(
            "/api/v1/directions/raw",
            params={"olat": 25.0, "olng": 121.0, "dlat": 25.01, "dlng": 121.01},
        )
    assert resp.status_code == 200
    assert len(resp.json()["routes"]) == 1


@pytest.mark.asyncio
async def test_calculate_walking_only(client) -> None:
    req = DirectionsRequest(
        origin_latitude=25.0,
        origin_longitude=121.0,
        destination_latitude=25.01,
        destination_longitude=121.01,
        modes=["walking"],
    )
    route = RouteOption(
        mode="walking",
        duration_seconds=600,
        distance_meters=800,
        available=True,
        steps=[],
    )
    with patch(
        "app.api.v1.endpoints.directions._google_route",
        AsyncMock(return_value=route),
    ):
        resp = await client.post("/api/v1/directions/calculate", json=req.model_dump())
    assert resp.status_code == 200
    assert resp.json()["routes"][0]["mode"] == "walking"


@pytest.mark.asyncio
async def test_calculate_transit_and_youbike(client) -> None:
    req = DirectionsRequest(
        origin_latitude=25.0,
        origin_longitude=121.0,
        destination_latitude=25.02,
        destination_longitude=121.02,
        modes=["transit_bus", "transit_mrt", "youbike"],
    )
    transit = RouteOption(
        mode="transit_bus",
        duration_seconds=900,
        distance_meters=2000,
        available=True,
        steps=[],
    )
    youbike = RouteOption(
        mode="youbike",
        duration_seconds=1200,
        distance_meters=1500,
        available=True,
        steps=[],
    )
    with (
        patch("app.api.v1.endpoints.directions._google_route", AsyncMock(return_value=transit)),
        patch("app.api.v1.endpoints.directions._youbike_route", AsyncMock(return_value=youbike)),
    ):
        resp = await client.post("/api/v1/directions/calculate", json=req.model_dump())
    modes = {r["mode"] for r in resp.json()["routes"]}
    assert "transit_bus" in modes
    assert "transit_mrt" in modes
    assert "youbike" in modes


@pytest.mark.asyncio
async def test_google_route_success_with_steps() -> None:
    from app.api.v1.endpoints.directions import _google_route

    g = AsyncMock()
    g.directions = AsyncMock(
        return_value={
            "routes": [
                {
                    "legs": [
                        {
                            "duration": {"value": 300},
                            "distance": {"value": 400},
                            "steps": [
                                {
                                    "html_instructions": "<b>往北</b>走",
                                    "duration": {"value": 300},
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    )
    req = DirectionsRequest(
        origin_latitude=25.0,
        origin_longitude=121.0,
        destination_latitude=25.01,
        destination_longitude=121.01,
        modes=["walking"],
    )
    result = await _google_route(g, req, mode="walking", our_mode="walking")
    assert result.available is True
    assert "往北" in result.steps[0].instruction


@pytest.mark.asyncio
async def test_google_route_no_routes() -> None:
    from app.api.v1.endpoints.directions import _google_route

    g = AsyncMock()
    g.directions = AsyncMock(return_value={"routes": []})
    req = DirectionsRequest(
        origin_latitude=1,
        origin_longitude=2,
        destination_latitude=3,
        destination_longitude=4,
        modes=["walking"],
    )
    result = await _google_route(g, req, mode="walking", our_mode="walking")
    assert result.available is False


@pytest.mark.asyncio
async def test_youbike_route_no_rent() -> None:
    from app.api.v1.endpoints.directions import _youbike_route

    db = AsyncMock()
    redis = AsyncMock()
    req = DirectionsRequest(
        origin_latitude=25.0,
        origin_longitude=121.0,
        destination_latitude=25.01,
        destination_longitude=121.01,
        modes=["youbike"],
    )
    with patch(
        "app.api.v1.endpoints.directions.transit_service.nearest_youbike",
        AsyncMock(return_value=[]),
    ):
        result = await _youbike_route(db, redis, req)
    assert result.available is False


@pytest.mark.asyncio
async def test_youbike_route_success() -> None:
    from app.api.v1.endpoints.directions import _youbike_route

    station = YoubikeStationResponse(
        station_id="S1",
        name="Rent",
        latitude=25.0,
        longitude=121.0,
        distance_meters=120.0,
        available_rent=3,
        available_return=0,
        bike_type="YouBike2.0",
    )
    ret_station = YoubikeStationResponse(
        station_id="S2",
        name="Return",
        latitude=25.01,
        longitude=121.01,
        distance_meters=80.0,
        available_rent=0,
        available_return=2,
        bike_type="YouBike2.0",
    )
    req = DirectionsRequest(
        origin_latitude=25.0,
        origin_longitude=121.0,
        destination_latitude=25.01,
        destination_longitude=121.01,
        modes=["youbike"],
    )
    with patch(
        "app.api.v1.endpoints.directions.transit_service.nearest_youbike",
        AsyncMock(side_effect=[[station], [ret_station]]),
    ):
        result = await _youbike_route(AsyncMock(), AsyncMock(), req)
    assert result.available is True
    assert len(result.steps) == 3
