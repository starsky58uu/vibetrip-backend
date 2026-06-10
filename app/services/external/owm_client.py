"""
OpenWeatherMap client — 當前天氣 + 5 日預報。
API docs: https://openweathermap.org/api

快取策略：
- current: 10 分鐘
- forecast: 30 分鐘

這裡只負責「打 API」，快取與聚合邏輯寫在 services/weather_service.py。
"""

from typing import Any

import httpx

from app.core.config import settings

OWM_BASE = "https://api.openweathermap.org/data/2.5"


class OpenWeatherMapClient:
    """打 OpenWeatherMap 的薄包裝。"""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=8.0)

    async def __aenter__(self) -> "OpenWeatherMapClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._http.aclose()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        resp = await self._http.get(
            f"{OWM_BASE}{path}",
            params={
                "appid": settings.OPENWEATHER_API_KEY,
                "units": "metric",  # 攝氏
                "lang": "zh_tw",
                **params,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        return await self._get("/weather", lat=lat, lon=lon)

    async def forecast_5day(self, lat: float, lon: float) -> dict[str, Any]:
        """每 3 小時一筆，共 40 筆 (5 天 × 8)。"""
        return await self._get("/forecast", lat=lat, lon=lon)
