"""Places / Weather / Taste / Transit 端點測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.places import PlaceResponse
from app.schemas.transit import (
    BusEtaResponse,
    MrtEtaResponse,
    YoubikeListResponse,
    YoubikeStationResponse,
)
from app.schemas.weather import CurrentWeatherResponse, ForecastResponse


@pytest.mark.asyncio
async def test_places_nearby(client) -> None:
    places = [PlaceResponse(place_id="p", name="Cafe", latitude=25.0, longitude=121.0)]
    with patch("app.api.v1.endpoints.places.places_service.nearby", AsyncMock(return_value=places)):
        resp = await client.get(
            "/api/v1/places/nearby",
            params={"lat": 25.0, "lon": 121.0, "category": "cafe"},
        )
    assert resp.status_code == 200
    assert resp.json()["places"][0]["name"] == "Cafe"


@pytest.mark.asyncio
async def test_places_search(client) -> None:
    with patch(
        "app.api.v1.endpoints.places.places_service.text_search", AsyncMock(return_value=[])
    ):
        resp = await client.get("/api/v1/places/search", params={"query": "咖啡"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_weather_current(client) -> None:
    from datetime import UTC, datetime

    w = CurrentWeatherResponse(
        temperature=20.0,
        feels_like=20.0,
        condition="Clear",
        description="晴",
        icon="01d",
        humidity=50,
        wind_speed=1.0,
        pressure=1010,
        observed_at=datetime.now(UTC),
        greeting="午安",
    )
    with patch(
        "app.api.v1.endpoints.weather.weather_service.get_current", AsyncMock(return_value=w)
    ):
        resp = await client.get("/api/v1/weather/current", params={"lat": 25.0, "lon": 121.0})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_weather_forecast(client) -> None:
    f = ForecastResponse(hourly=[], daily=[])
    with patch(
        "app.api.v1.endpoints.weather.weather_service.get_forecast", AsyncMock(return_value=f)
    ):
        resp = await client.get("/api/v1/weather/forecast", params={"lat": 25.0, "lon": 121.0})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_taste_profile(authed_client) -> None:
    data = {
        "generated": False,
        "spots_count": 1,
        "headline": "h",
        "subtitle": "s",
        "tags": [],
        "roaming_style": "x",
        "top_vibes": [],
    }
    with patch(
        "app.api.v1.endpoints.taste.taste_service.get_taste_profile", AsyncMock(return_value=data)
    ):
        resp = await authed_client.get("/api/v1/taste/profile?refresh=true")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_transit_endpoints(client) -> None:
    from datetime import UTC, datetime

    bus = BusEtaResponse(
        route_name="207",
        stop_name="站",
        eta_seconds=60,
        plate_number=None,
        status="in_transit",
        fetched_at=datetime.now(UTC),
    )
    mrt = MrtEtaResponse(station_name="市政府", next_trains=[], fetched_at=datetime.now(UTC))
    bikes = YoubikeListResponse(
        stations=[
            YoubikeStationResponse(
                station_id="S1",
                name="A",
                latitude=25.0,
                longitude=121.0,
                distance_meters=100.0,
                available_rent=3,
                available_return=2,
                bike_type="YouBike2.0",
            )
        ]
    )
    with (
        patch(
            "app.api.v1.endpoints.transit.transit_service.get_bus_eta", AsyncMock(return_value=bus)
        ),
        patch(
            "app.api.v1.endpoints.transit.transit_service.get_mrt_eta", AsyncMock(return_value=mrt)
        ),
        patch(
            "app.api.v1.endpoints.transit.transit_service.nearest_youbike",
            AsyncMock(return_value=bikes.stations),
        ),
    ):
        r1 = await client.get(
            "/api/v1/transit/bus/eta", params={"route_name": "207", "stop_name": "站"}
        )
        r2 = await client.get("/api/v1/transit/mrt/eta", params={"station_name": "市政府"})
        r3 = await client.get(
            "/api/v1/transit/bikes",
            params={"lat": 25.0, "lon": 121.0, "type": "rent"},
        )
    assert r1.status_code == r2.status_code == r3.status_code == 200
