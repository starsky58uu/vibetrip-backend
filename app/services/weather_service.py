"""
天氣服務層 — 代理 OpenWeatherMap + Redis 快取。

快取流程：
1. 收到 (lat, lon) → 先四捨五入到小數第 2 位，避免一樣的區域重複打 OWM
2. 看 Redis 有沒有 → 有就直接回
3. 沒有就打 OWM、存 Redis (TTL 10 分鐘)

這是最典型的「動態資料放 Redis」範例。
"""
from datetime import datetime, timezone

import redis.asyncio as redis

from app.core.redis_client import build_key, cache_get_json, cache_set_json
from app.schemas.weather import (
    CurrentWeatherResponse,
    DailyForecast,
    ForecastResponse,
    HourlyForecast,
)
from app.services.external.owm_client import OpenWeatherMapClient


CURRENT_TTL = 10 * 60      # 10 分鐘
FORECAST_TTL = 30 * 60     # 30 分鐘


async def get_current(r: redis.Redis, lat: float, lon: float) -> CurrentWeatherResponse:
    """取當前天氣 (有快取)。"""
    key = build_key("weather", "current", round(lat, 2), round(lon, 2))
    cached = await cache_get_json(r, key)
    if cached:
        return CurrentWeatherResponse.model_validate(cached)

    async with OpenWeatherMapClient() as owm:
        raw = await owm.current_weather(lat, lon)

    weather = raw.get("weather", [{}])[0]
    main = raw.get("main", {})
    wind = raw.get("wind", {})

    result = CurrentWeatherResponse(
        temperature=main.get("temp", 0.0),
        feels_like=main.get("feels_like", 0.0),
        condition=weather.get("main", "Unknown"),
        description=weather.get("description", ""),
        icon=weather.get("icon", "01d"),
        humidity=main.get("humidity", 0),
        wind_speed=wind.get("speed", 0.0),
        pressure=main.get("pressure", 0),
        observed_at=datetime.now(timezone.utc),
        district=raw.get("name"),
        greeting=_build_greeting(weather.get("main", ""), datetime.now().hour),
    )

    await cache_set_json(r, key, result.model_dump(mode="json"), ttl_seconds=CURRENT_TTL)
    return result


async def get_forecast(r: redis.Redis, lat: float, lon: float) -> ForecastResponse:
    """5 日預報 (3 小時一筆)。"""
    key = build_key("weather", "forecast", round(lat, 2), round(lon, 2))
    cached = await cache_get_json(r, key)
    if cached:
        return ForecastResponse.model_validate(cached)

    async with OpenWeatherMapClient() as owm:
        raw = await owm.forecast_5day(lat, lon)

    # 整理每小時資料
    hourly = [
        HourlyForecast(
            time=datetime.fromtimestamp(item["dt"], tz=timezone.utc),
            temperature=item["main"]["temp"],
            condition=item["weather"][0]["main"],
            icon=item["weather"][0]["icon"],
            precipitation_prob=item.get("pop", 0.0),
        )
        for item in raw.get("list", [])
    ]

    # 按日期聚合成 daily
    daily_map: dict[str, dict] = {}
    for h in hourly:
        date_key = h.time.astimezone().strftime("%Y-%m-%d")
        agg = daily_map.setdefault(
            date_key,
            {"min": h.temperature, "max": h.temperature, "condition": h.condition, "icon": h.icon},
        )
        agg["min"] = min(agg["min"], h.temperature)
        agg["max"] = max(agg["max"], h.temperature)

    daily = [
        DailyForecast(
            date=date,
            temp_min=v["min"],
            temp_max=v["max"],
            condition=v["condition"],
            icon=v["icon"],
        )
        for date, v in sorted(daily_map.items())
    ]

    result = ForecastResponse(hourly=hourly, daily=daily)
    await cache_set_json(r, key, result.model_dump(mode="json"), ttl_seconds=FORECAST_TTL)
    return result


def _build_greeting(condition: str, hour: int) -> str:
    """產生首頁的招呼語 (取代前端的 greetingMessage 邏輯)。"""
    time_label = (
        "清晨" if 5 <= hour < 9 else
        "早安" if 9 <= hour < 12 else
        "午安" if 12 <= hour < 17 else
        "傍晚" if 17 <= hour < 19 else
        "晚安"
    )

    weather_hint = {
        "Clear": "天氣不錯，出門走走吧 ☀️",
        "Clouds": "雲有點多，溫度剛好散步 ☁️",
        "Rain": "下雨了，躲進咖啡店吧 ☔️",
        "Thunderstorm": "打雷了！待在室內最安全 ⛈️",
        "Snow": "下雪了 ❄️",
    }.get(condition, "今天想去哪呢？")

    return f"{time_label}，{weather_hint}"
