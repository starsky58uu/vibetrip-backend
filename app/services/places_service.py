"""
Google Places 代理服務。

快取：同樣條件 (座標+類別+半徑) 1 小時內重複打直接回 Redis。
"""

import redis.asyncio as redis

from app.core.redis_client import build_key, cache_get_json, cache_set_json
from app.schemas.places import PlaceCategory, PlaceResponse
from app.services.external.google_client import GoogleMapsClient

CACHE_TTL = 60 * 60


# 前端 arData.js 的 CATEGORY_MAP → Google Places 的 type
CATEGORY_TO_GOOGLE_TYPE = {
    "convenience_store": "convenience_store",
    "cafe": "cafe",
    "restaurant": "restaurant",
    "drink_shop": "cafe",  # Google 沒「飲料店」類別，用 cafe 近似
}


async def nearby(
    r: redis.Redis,
    lat: float,
    lon: float,
    category: PlaceCategory,
    radius_meters: int,
) -> list[PlaceResponse]:
    key = build_key("places", "nearby", round(lat, 3), round(lon, 3), category, radius_meters)
    cached = await cache_get_json(r, key)
    if cached:
        return [PlaceResponse.model_validate(x) for x in cached]

    async with GoogleMapsClient() as g:
        raw = await g.nearby_search(lat, lon, CATEGORY_TO_GOOGLE_TYPE[category], radius_meters)

    places = [_map_place(item, origin=(lat, lon)) for item in raw]

    await cache_set_json(
        r,
        key,
        [p.model_dump(mode="json") for p in places],
        ttl_seconds=CACHE_TTL,
    )
    return places


async def text_search(
    r: redis.Redis,
    query: str,
    lat: float | None,
    lon: float | None,
) -> list[PlaceResponse]:
    key = build_key("places", "search", query, round(lat or 0, 2), round(lon or 0, 2))
    cached = await cache_get_json(r, key)
    if cached:
        return [PlaceResponse.model_validate(x) for x in cached]

    async with GoogleMapsClient() as g:
        raw = await g.text_search(query, lat, lon)

    origin = (lat, lon) if lat is not None and lon is not None else None
    places = [_map_place(item, origin=origin) for item in raw]

    await cache_set_json(
        r,
        key,
        [p.model_dump(mode="json") for p in places],
        ttl_seconds=30 * 60,
    )
    return places


def _map_place(raw: dict, origin: tuple[float, float] | None) -> PlaceResponse:
    """把 Google Places 的 JSON 轉成我們的 schema。"""
    geo = raw.get("geometry", {}).get("location", {})
    lat = geo.get("lat", 0.0)
    lon = geo.get("lng", 0.0)

    return PlaceResponse(
        place_id=raw.get("place_id", ""),
        name=raw.get("name", ""),
        latitude=lat,
        longitude=lon,
        distance_meters=_haversine(origin, (lat, lon)) if origin else None,
        rating=raw.get("rating"),
        is_open_now=raw.get("opening_hours", {}).get("open_now"),
        categories=raw.get("types", []),
        formatted_address=raw.get("formatted_address") or raw.get("vicinity"),
    )


def _haversine(a: tuple[float, float] | None, b: tuple[float, float]) -> float | None:
    """
    Haversine 算兩點距離 (公尺)。

    備註：這是少數我們自己算距離的場景 —
    因為 Google 回傳的資料本身沒距離欄位，又不適合每筆都塞進 DB 再查 PostGIS。
    凡是資料已經在 DB 裡的 (公車站/YouBike)，一律交給 PostGIS 算。
    """
    import math

    if a is None:
        return None
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371000  # 地球半徑 (公尺)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(h)), 1)
