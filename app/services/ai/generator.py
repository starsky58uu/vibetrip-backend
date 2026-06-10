"""
AI 行程生成主流程。

流程：Google Places → Groq → 驗證 → 距離補全。
"""

import logging
from datetime import datetime
from uuid import UUID

from app.core.redis_client import build_key, cache_get_json, cache_set_json, get_redis
from app.services.ai.constants import CACHE_TTL, TW_TZ
from app.services.ai.enrichment import enrich_distances
from app.services.ai.groq import call_groq
from app.services.ai.places import (
    fetch_closing_times,
    filter_closing_soon,
    search_nearby,
    validate_closing_times,
)
from app.services.ai.validation import validate_activities

logger = logging.getLogger(__name__)


async def generate_trip(
    vibe_key: str,
    lat: float,
    lon: float,
    weather: str | None,
    exclude_trip_ids: list[UUID] | None = None,
) -> dict:
    """
    三步驟生成行程：
      1. Google Places 查真實附近店家（含座標）
      2. Groq LLaMA 從清單選地點 + 生成描述
      3. Google Directions 算真實步行距離

    exclude_trip_ids 非空時跳過快取讀取，確保搖一搖每次都有新結果。
    """
    redis = await get_redis()
    now_for_key = datetime.now(TW_TZ)
    h = now_for_key.hour
    hour_slot = h if (h >= 22 or h < 6) else h // 2
    key = build_key("trip", "ai", vibe_key, f"{lat:.2f}", f"{lon:.2f}", hour_slot)

    use_cache = not exclude_trip_ids
    if use_cache:
        cached = await cache_get_json(redis, key)
        if cached:
            return cached

    nearby = await search_nearby(vibe_key, lat, lon)

    if nearby and datetime.now(TW_TZ).hour >= 17:
        await fetch_closing_times(nearby)
        nearby = filter_closing_soon(nearby, min_stay_min=15)

    result = await call_groq(vibe_key, lat, lon, weather, nearby)

    if nearby and result.get("items"):
        result["items"] = validate_activities(result["items"], nearby)

    if nearby and result.get("items"):
        result["items"] = validate_closing_times(result["items"], nearby)

    try:
        result["items"] = await enrich_distances(result["items"], lat, lon, nearby)
    except Exception as e:
        logger.warning("距離補正失敗: %s", e)

    await cache_set_json(redis, key, result, ttl_seconds=CACHE_TTL)
    return result
