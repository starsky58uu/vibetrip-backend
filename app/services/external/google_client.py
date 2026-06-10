"""
Google Maps Platform client — Places + Directions。
"""

from typing import Any

import httpx

from app.core.config import settings

GOOGLE_BASE = "https://maps.googleapis.com/maps/api"

# HTTP 200 但 API 層失敗的 status；ZERO_RESULTS 視為正常空結果
_OK_STATUSES = frozenset({"OK", "ZERO_RESULTS"})


class GoogleMapsError(Exception):
    """Google API 回傳非 OK status（例如 REQUEST_DENIED、OVER_QUERY_LIMIT）。"""

    def __init__(self, status: str, message: str = "") -> None:
        self.status = status
        super().__init__(message or status)


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
            params={"key": settings.GOOGLE_MAPS_API_KEY, "language": "zh-TW", **params},
        )
        resp.raise_for_status()
        data = resp.json()
        api_status = data.get("status", "OK")
        if api_status not in _OK_STATUSES:
            raise GoogleMapsError(api_status, data.get("error_message", api_status))
        return data

    async def nearby_search(
        self,
        lat: float,
        lon: float,
        place_type: str,
        radius_meters: int = 500,
    ) -> list[dict[str, Any]]:
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
        radius_meters: int = 5000,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query}
        if lat is not None and lon is not None:
            params["location"] = f"{lat},{lon}"
            params["radius"] = radius_meters
        data = await self._get("/place/textsearch/json", **params)
        return data.get("results", [])

    async def place_details(
        self,
        place_id: str,
        fields: str = "opening_hours",
    ) -> dict[str, Any]:
        data = await self._get(
            "/place/details/json",
            place_id=place_id,
            fields=fields,
        )
        return data.get("result", {})

    async def directions(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "walking",
        departure_time: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "origin": f"{origin_lat},{origin_lon}",
            "destination": f"{dest_lat},{dest_lon}",
            "mode": mode,
        }
        if departure_time is not None:
            params["departure_time"] = departure_time
        return await self._get("/directions/json", **params)
