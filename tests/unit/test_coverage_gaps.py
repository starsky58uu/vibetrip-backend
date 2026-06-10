"""補齊剩餘分支的 targeted coverage tests。"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import decode_token_jti
from app.schemas.trip import RecommendRequest
from app.services import places_service, spot_service, taste_service, transit_service, trip_service
from app.services.ai import (
    generator as ai_generator,
    groq as ai_groq,
    places as ai_places,
    validation as ai_validation,
)
from app.services.external.google_client import GoogleMapsClient

# ── security / users ──────────────────────────────────────────────────────────


def test_decode_token_jti_missing_sub() -> None:
    payload = {"type": "access", "jti": "x", "exp": 9999999999}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(JWTError, match="sub"):
        decode_token_jti(token, expected_type="access")


# ── trip_service ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recommend_from_db_with_exclude_fallback() -> None:
    db = AsyncMock()
    template = MagicMock()
    template.id = uuid4()
    template.vibe_key = "walk"
    template.title = "fallback"
    template.items = []
    empty = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    filled = MagicMock(
        scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[template])))
    )
    db.execute = AsyncMock(side_effect=[empty, filled])
    with (
        patch("app.services.trip_service.generate_trip", AsyncMock(side_effect=RuntimeError("x"))),
        patch("app.services.trip_service.random.choice", return_value=template),
    ):
        result = await trip_service.recommend(
            db,
            RecommendRequest(
                vibe_key="walk", latitude=25.0, longitude=121.0, exclude_trip_ids=[uuid4()]
            ),
        )
    assert result.title == "fallback"


# ── places_service cache hit ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_places_nearby_cache_hit() -> None:
    redis = AsyncMock()
    payload = [
        {
            "place_id": "p",
            "name": "C",
            "latitude": 25.0,
            "longitude": 121.0,
            "distance_meters": 10.0,
            "rating": 4.0,
            "is_open_now": True,
            "categories": [],
            "formatted_address": "a",
        }
    ]
    redis.get = AsyncMock(return_value=json.dumps(payload))
    places = await places_service.nearby(redis, 25.0, 121.0, "cafe", 500)
    assert places[0].name == "C"


@pytest.mark.asyncio
async def test_places_text_search_cache_hit() -> None:
    cached = [
        {
            "place_id": "p",
            "name": "Q",
            "latitude": 25.0,
            "longitude": 121.0,
            "distance_meters": None,
            "rating": None,
            "is_open_now": None,
            "categories": [],
            "formatted_address": None,
        }
    ]
    with patch("app.services.places_service.cache_get_json", AsyncMock(return_value=cached)):
        places = await places_service.text_search(AsyncMock(), "q", None, None)
    assert places[0].name == "Q"


# ── google text_search branches ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_text_search_with_location() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "OK", "results": []})
    client = GoogleMapsClient()
    client._http = AsyncMock()
    client._http.get = AsyncMock(return_value=mock_resp)
    await client.text_search("coffee", lat=25.0, lon=121.0)


# ── transit ───────────────────────────────────────────────────────────────────


def test_parse_bus_eta_stop_status_2_no_eta() -> None:
    result = transit_service._parse_bus_eta({"StopStatus": 2, "EstimateTime": None}, "r", "s")
    assert result.status == "no_service"


@pytest.mark.asyncio
async def test_get_mrt_eta_cache_hit() -> None:
    redis = AsyncMock()
    payload = {
        "station_name": "市政府",
        "next_trains": [],
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    redis.get = AsyncMock(return_value=json.dumps(payload))
    result = await transit_service.get_mrt_eta(redis, AsyncMock(), "市政府")
    assert result.station_name == "市政府"


@pytest.mark.asyncio
async def test_load_youbike_status_fetch() -> None:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    mock_tdx = AsyncMock()
    mock_tdx.__aenter__ = AsyncMock(return_value=mock_tdx)
    mock_tdx.__aexit__ = AsyncMock(return_value=None)
    mock_tdx.get_youbike_stations_status = AsyncMock(
        return_value=[{"StationID": "S1", "AvailableRentBikes": 1, "AvailableReturnBikes": 2}]
    )
    with patch("app.services.transit_service.TDXClient", return_value=mock_tdx):
        data = await transit_service._load_youbike_status(redis)
    assert data["S1"]["available_rent"] == 1


@pytest.mark.asyncio
async def test_nearest_youbike_skip_zero_return() -> None:
    redis = AsyncMock()
    db = AsyncMock()
    row = {
        "tdx_station_id": "S1",
        "name": "A",
        "lat": 25.0,
        "lon": 121.0,
        "bike_type": "YouBike2.0",
        "distance_m": 50.0,
    }
    db.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    with patch(
        "app.services.transit_service._load_youbike_status",
        AsyncMock(return_value={"S1": {"available_rent": 1, "available_return": 0}}),
    ):
        assert await transit_service.nearest_youbike(redis, db, 25.0, 121.0, "return") == []


# ── taste_service full groq path ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_taste_profile_full_generation() -> None:
    user_id = uuid4()
    spots = []
    for i in range(4):
        s = MagicMock()
        s.created_at = datetime(2026, 1, 1, 10 + i)
        s.note = f"n{i}"
        s.image_url = None
        spots.append(s)
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=spots)))
        )
    )
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    with (
        patch("app.services.taste_service.get_redis", AsyncMock(return_value=mock_redis)),
        patch(
            "app.services.taste_service._generate_with_groq",
            AsyncMock(
                return_value={
                    "generated": True,
                    "spots_count": 4,
                    "headline": "h",
                    "subtitle": "s",
                    "tags": ["夜行"],
                    "roaming_style": "r",
                    "top_vibes": ["Café Drift"],
                }
            ),
        ),
    ):
        result = await taste_service.get_taste_profile(db, user_id, refresh=True)
    assert result["generated"] is True


# ── ai generator evening branch ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_trip_evening_closing_filter() -> None:
    nearby = [{"name": "A", "rating": 4.0}]
    with (
        patch("app.services.ai.generator.get_redis", AsyncMock(return_value=AsyncMock())),
        patch("app.services.ai.generator.cache_get_json", AsyncMock(return_value=None)),
        patch("app.services.ai.generator.cache_set_json", AsyncMock()),
        patch("app.services.ai.generator.search_nearby", AsyncMock(return_value=nearby)),
        patch("app.services.ai.generator.fetch_closing_times", AsyncMock()) as fetch,
        patch("app.services.ai.generator.filter_closing_soon", return_value=nearby) as filt,
        patch(
            "app.services.ai.generator.call_groq",
            AsyncMock(return_value={"title": "T", "items": []}),
        ),
        patch("app.services.ai.generator.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = datetime(2026, 6, 10, 18, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        await ai_generator.generate_trip("cafe", 25.0, 121.0, None)
    fetch.assert_awaited_once()
    filt.assert_called_once()


# ── ai groq formatting branches ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_groq_formats_closing_tags() -> None:
    nearby = [
        {"name": "24h店", "rating": 4.0, "address": "a", "closes_at": "24:00"},
        {"name": "早關", "rating": 4.0, "address": "b", "closes_at": "01:00↑"},
        {"name": "一般", "rating": 4.0, "address": "c", "closes_at": "21:30"},
        {"name": "未知", "rating": 4.0, "address": "d"},
    ]
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"title":"t","items":[]}'))]
    with patch("app.services.ai.groq.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch("app.services.ai.groq.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await ai_groq.call_groq("cafe", 25.0, 121.0, "Rain", nearby)


@pytest.mark.asyncio
async def test_call_groq_daytime_empty_nearby() -> None:
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"title":"t","items":[]}'))]
    with patch("app.services.ai.groq.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch("app.services.ai.groq.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Taipei"))
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await ai_groq.call_groq("walk", 25.0, 121.0, None, [])


# ── ai places branches ────────────────────────────────────────────────────────


def test_filter_closing_invalid_time_kept() -> None:
    assert ai_places.filter_closing_soon([{"closes_at": "bad"}], 30)


def test_validate_closing_empty_inputs() -> None:
    assert ai_validation.validate_activities([], [{"name": "A"}]) == []


@pytest.mark.asyncio
async def test_search_nearby_supplement_and_filters(monkeypatch) -> None:
    tw = datetime(2026, 6, 10, 23, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    far = {
        "name": "Far",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 30.0, "lng": 130.0}},
        "opening_hours": {"open_now": True},
    }
    closed = {
        "name": "Closed",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": False},
    }
    low = {
        "name": "Low",
        "formatted_address": "a",
        "rating": 2.0,
        "types": ["cafe"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": True},
    }
    landmark = {
        "name": "Park",
        "formatted_address": "a",
        "rating": 0,
        "types": ["park"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
    }
    dup = {
        "name": "Dup",
        "formatted_address": "a",
        "rating": 4.0,
        "types": ["bar"],
        "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
        "opening_hours": {"open_now": True},
        "business_status": "CLOSED_PERMANENTLY",
    }
    with (
        patch("app.services.ai.places.datetime") as mock_dt,
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=AsyncMock())),
        patch(
            "app.services.ai.places.cached_text_search",
            AsyncMock(side_effect=[[closed, low, landmark, dup], [far]]),
        ),
        patch("app.services.ai.places.random.sample", return_value=["咖啡"]),
    ):
        mock_dt.now.return_value = tw
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        results = await ai_places.search_nearby("cafe", 25.033, 121.565)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_fetch_closing_no_place_id_and_api_error() -> None:
    places = [{"name": "X"}, {"place_id": "p", "name": "Y"}]
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.place_details = AsyncMock(side_effect=RuntimeError("fail"))
    with (
        patch("app.services.ai.places.get_redis", AsyncMock(return_value=redis)),
        patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g),
    ):
        await ai_places.fetch_closing_times(places)


# ── spot_service unit with mocks ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spot_service_errors_and_toggles() -> None:
    owner = MagicMock()
    owner.id = uuid4()
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException):
        await spot_service.update_personal_spot(db, owner, uuid4(), MagicMock())
    with pytest.raises(HTTPException):
        await spot_service.delete_personal_spot(db, owner, uuid4())
    with pytest.raises(HTTPException):
        await spot_service.toggle_like(db, owner, uuid4())


# ── directions youbike no return ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_youbike_route_no_return_station() -> None:
    from app.api.v1.endpoints.directions import _youbike_route
    from app.schemas.transit import DirectionsRequest, YoubikeStationResponse

    rent = YoubikeStationResponse(
        station_id="S1",
        name="R",
        latitude=25.0,
        longitude=121.0,
        distance_meters=100.0,
        available_rent=1,
        available_return=0,
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
        AsyncMock(side_effect=[[rent], []]),
    ):
        result = await _youbike_route(AsyncMock(), AsyncMock(), req)
    assert result.available is False


# ── weather forecast cache hit ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weather_forecast_cache_hit() -> None:
    from app.services.weather_service import get_forecast

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=json.dumps({"hourly": [], "daily": []}))
    result = await get_forecast(redis, 25.033, 121.565)
    assert result.hourly == []


# ── init_db main ─────────────────────────────────────────────────────────────


def test_init_db_main_entrypoint(monkeypatch) -> None:
    monkeypatch.setattr("app.db.init_db.asyncio.run", MagicMock())
    import runpy

    runpy.run_module("app.db.init_db", run_name="__main__")
