"""
TDX (交通部 PTX/TDX) client — 負責從 TDX 平台撈公車/捷運/YouBike 的即時資料。

認證：OAuth2 client credentials flow
- POST 認證 endpoint 拿 access_token (有效 1 天)
- 後續 API 呼叫帶 Authorization: Bearer <token>

我們會把 access_token 快取在 Redis (24 小時 TTL)，避免每次 API 呼叫都去重新認證。

docs: https://tdx.transportdata.tw/api-service/swagger
"""
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.redis_client import build_key, cache_get_json, cache_set_json, get_redis


# TDX 認證與 API endpoint
TDX_AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
TDX_API_BASE = "https://tdx.transportdata.tw/api/basic"


class TDXClient:
    """
    封裝 TDX API 呼叫。
    使用方式：
        async with TDXClient() as tdx:
            data = await tdx.get_bus_eta("207", "市政府站")
    """

    def __init__(self) -> None:
        # 共用的 httpx client — 使用 connection pooling 比每次新開快得多
        self._http = httpx.AsyncClient(timeout=10.0)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def __aenter__(self) -> "TDXClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._http.aclose()

    # ---------- 認證 ----------
    async def _get_access_token(self) -> str:
        """
        取得 TDX access_token。
        快取流程：
        1. 先看 Redis 有沒有
        2. 沒有的話去 TDX 拿，拿到後存 Redis (TTL 23 小時，避免剛好過期的 edge case)
        """
        # 先檢查記憶體快取
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        # 再檢查 Redis
        redis = await get_redis()
        cached = await cache_get_json(redis, build_key("tdx", "token"))
        if cached:
            self._token = cached["access_token"]
            self._token_expires_at = cached["expires_at"]
            return self._token

        # 最後才去 TDX 拿新的
        resp = await self._http.post(
            TDX_AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.TDX_CLIENT_ID,
                "client_secret": settings.TDX_CLIENT_SECRET,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        token = body["access_token"]
        expires_at = time.time() + body.get("expires_in", 86400)

        self._token = token
        self._token_expires_at = expires_at

        # 存 Redis 供別的 worker 共用 (TTL 稍短一點避過期)
        await cache_set_json(
            redis,
            build_key("tdx", "token"),
            {"access_token": token, "expires_at": expires_at},
            ttl_seconds=int(body.get("expires_in", 86400)) - 600,
        )
        return token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """發 GET request，自動帶 Bearer token。"""
        token = await self._get_access_token()
        resp = await self._http.get(
            f"{TDX_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"},
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json()

    # ---------- 實際 API ----------
    async def get_bus_eta(
        self,
        city: str,
        route_name: str,
        stop_name: str,
    ) -> dict[str, Any] | None:
        """
        查某條公車路線、某站的即時到站時間。

        TDX API: GET /v2/Bus/EstimatedTimeOfArrival/City/{City}/{RouteName}
        回傳第一筆符合 stop_name 的記錄。
        """
        data = await self._get(
            f"/v2/Bus/EstimatedTimeOfArrival/City/{city}/{route_name}",
            params={"$format": "JSON", "$top": 100},
        )
        for item in data:
            if item.get("StopName", {}).get("Zh_tw") == stop_name:
                return item
        return None

    async def get_mrt_eta(self, station_id: str) -> list[dict[str, Any]]:
        """查捷運某站各方向的到站時間。"""
        data = await self._get(
            f"/v2/Rail/Metro/LiveBoard/TRTC",
            params={"$filter": f"StationID eq '{station_id}'", "$format": "JSON"},
        )
        return data

    async def get_youbike_stations_status(self, city: str = "Taipei") -> list[dict[str, Any]]:
        """
        取得整個城市所有 YouBike 站的即時可借/可還車輛數。
        因為 TDX 一次吐 1000+ 筆，我們把結果放 Redis 當短暫快取 (30 秒)，
        然後在 service 層用 PostGIS 找出使用者附近的站點。
        """
        data = await self._get(
            f"/v2/Bike/Availability/{city}",
            params={"$format": "JSON", "$top": 2000},
        )
        return data
