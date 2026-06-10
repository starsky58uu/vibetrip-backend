"""Places 服務測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.places_service import _haversine, _map_place, nearby, text_search


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int = 0) -> None:
        self._store[key] = value


def test_haversine_none_origin() -> None:
    assert _haversine(None, (25.0, 121.0)) is None


def test_haversine_distance() -> None:
    d = _haversine((25.033, 121.565), (25.034, 121.566))
    assert d is not None
    assert d > 0


def test_map_place_with_origin() -> None:
    raw = {
        "place_id": "pid",
        "name": "Test Cafe",
        "geometry": {"location": {"lat": 25.0, "lng": 121.0}},
        "rating": 4.5,
        "opening_hours": {"open_now": True},
        "types": ["cafe"],
        "formatted_address": "Addr",
    }
    place = _map_place(raw, origin=(25.033, 121.565))
    assert place.name == "Test Cafe"
    assert place.distance_meters is not None


def test_map_place_without_origin() -> None:
    raw = {
        "place_id": "pid",
        "name": "X",
        "geometry": {"location": {"lat": 25.0, "lng": 121.0}},
        "types": [],
        "vicinity": "Near",
    }
    place = _map_place(raw, origin=None)
    assert place.distance_meters is None
    assert place.formatted_address == "Near"


@pytest.mark.asyncio
async def test_nearby_fetches_google() -> None:
    redis = _FakeRedis()
    raw = [
        {
            "place_id": "p1",
            "name": "7-ELEVEN",
            "geometry": {"location": {"lat": 25.033, "lng": 121.565}},
            "rating": 4.0,
            "types": ["convenience_store"],
        }
    ]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.nearby_search = AsyncMock(return_value=raw)
    with patch("app.services.places_service.GoogleMapsClient", return_value=mock_g):
        places = await nearby(redis, 25.033, 121.565, "convenience_store", 500)
    assert len(places) >= 1
    assert places[0].name == "7-ELEVEN"


@pytest.mark.asyncio
async def test_text_search_with_coords() -> None:
    redis = _FakeRedis()
    raw = [
        {
            "place_id": "p1",
            "name": "Park",
            "geometry": {"location": {"lat": 25.03, "lng": 121.56}},
            "types": ["park"],
        }
    ]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(return_value=raw)
    with patch("app.services.places_service.GoogleMapsClient", return_value=mock_g):
        places = await text_search(redis, "公園", 25.03, 121.56)
    assert places[0].name == "Park"
    mock_g.text_search.assert_awaited_once()
