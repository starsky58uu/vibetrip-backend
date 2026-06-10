"""天氣服務測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.weather_service import _build_greeting, get_current, get_forecast


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int = 0) -> None:
        self._store[key] = value


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (6, "清晨"),
        (10, "早安"),
        (14, "午安"),
        (18, "傍晚"),
        (22, "晚安"),
    ],
)
def test_build_greeting_time_labels(hour: int, expected: str) -> None:
    assert expected in _build_greeting("Clear", hour)


@pytest.mark.parametrize(
    ("condition", "hint"),
    [
        ("Clear", "天氣不錯"),
        ("Clouds", "雲有點多"),
        ("Rain", "下雨了"),
        ("Thunderstorm", "打雷了"),
        ("Snow", "下雪了"),
        ("Fog", "今天想去哪"),
    ],
)
def test_build_greeting_weather_hints(condition: str, hint: str) -> None:
    assert hint in _build_greeting(condition, 12)


@pytest.mark.asyncio
async def test_get_current_cache_hit() -> None:
    redis = _FakeRedis()
    from app.core.redis_client import build_key, cache_set_json

    key = build_key("weather", "current", round(25.033, 2), round(121.565, 2))
    payload = {
        "temperature": 20.0,
        "feels_like": 20.0,
        "condition": "Clear",
        "description": "晴",
        "icon": "01d",
        "humidity": 50,
        "wind_speed": 1.0,
        "pressure": 1010,
        "observed_at": "2026-01-01T00:00:00+00:00",
        "district": "Taipei",
        "greeting": "午安",
    }
    await cache_set_json(redis, key, payload, ttl_seconds=60)
    result = await get_current(redis, 25.033, 121.565)
    assert result.condition == "Clear"


@pytest.mark.asyncio
async def test_get_current_fetches_from_api() -> None:
    redis = _FakeRedis()
    raw = {
        "weather": [{"main": "Rain", "description": "小雨", "icon": "10d"}],
        "main": {"temp": 18.0, "feels_like": 17.0, "humidity": 80, "pressure": 1005},
        "wind": {"speed": 2.0},
        "name": "Taipei",
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.current_weather = AsyncMock(return_value=raw)
    with patch("app.services.weather_service.OpenWeatherMapClient", return_value=mock_client):
        result = await get_current(redis, 25.0, 121.5)
    assert result.condition == "Rain"
    assert result.temperature == 18.0


@pytest.mark.asyncio
async def test_get_forecast_cache_miss() -> None:
    redis = _FakeRedis()
    raw = {
        "list": [
            {
                "dt": 1700000000,
                "main": {"temp": 22.0},
                "weather": [{"main": "Clear", "icon": "01d"}],
                "pop": 0.1,
            }
        ]
    }
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.forecast_5day = AsyncMock(return_value=raw)
    with patch("app.services.weather_service.OpenWeatherMapClient", return_value=mock_client):
        result = await get_forecast(redis, 25.0, 121.5)
    assert len(result.hourly) == 1
    assert len(result.daily) >= 1
