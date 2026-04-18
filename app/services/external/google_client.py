"""
Google Maps Platform client — Places + Directions。

為什麼不讓前端直接打？
1. Google API key 不能暴露在 App 裡 (會被盜用產生費用)
2. 後端能快取相同請求、控制速率

docs:
- https://developers.google.com/maps/documentation/places/web-service
- https://developers.google.com/maps/documentation/directions
"""
from typing import Any

import httpx

from app.core.config import settings


GOOGLE_BASE = "https://maps.googleapis.com/maps/api"


class GoogleMapsClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)

    async def __aenter__(self) -> "GoogleMapsClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._http.aclose()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        resp = await self._http.get(
            f"{GOOGLE_BASE}{path}",
            params={"key": settings.GOOGLE_API_KEY, "language": "zh-TW", **params},
        )
        resp.raise_for_status()
        return resp.json()

    # ---------- Places ----------
    async def nearby_search(
        self,
        lat: float,
        lon: float,
        place_type: str,
        radius_meters: int = 500,
    ) -> list[dict[str, Any]]:
        """附近搜尋，對應前端 AR 畫面的「附近超商/咖啡...」。"""
        data = await self._get(
            "/place/nearbysearch/json",
            location=f"{lat},{lon}",
            radius=radius_meters,
            type=place_type,
        )
        return data.get("results", [])

    async def text_search(
        self,
        query: str,
        lat: float | None = None,
        lon: float | None = None,
    ) -> list[dict[str, Any]]:
        """文字搜尋，對應 AR 畫面的搜尋框。"""
        params: dict[str, Any] = {"query": query}
        if lat is not None and lon is not None:
            params["location"] = f"{lat},{lon}"
            params["radius"] = 5000
        data = await self._get("/place/textsearch/json", **params)
        return data.get("results", [])

    # ---------- Directions ----------
    async def directions(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "walking",
    ) -> dict[str, Any]:
        """
        mode: walking / transit / bicycling / driving
        我們用 walking 得到步行路線、transit 得到公車/捷運換乘。
        """
        return await self._get(
            "/directions/json",
            origin=f"{origin_lat},{origin_lon}",
            destination=f"{dest_lat},{dest_lon}",
            mode=mode,
        )
