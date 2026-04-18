"""地點搜尋端點 — 代理 Google Places。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
import redis.asyncio as redis

from app.core.redis_client import get_redis
from app.schemas.places import PlaceCategory, PlaceListResponse
from app.services import places_service

router = APIRouter()


@router.get("/nearby", response_model=PlaceListResponse)
async def nearby_places(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    category: PlaceCategory,
    r: Annotated[redis.Redis, Depends(get_redis)],
    radius_meters: Annotated[int, Query(ge=50, le=2000)] = 500,
) -> PlaceListResponse:
    """附近的 XX (超商/咖啡/餐廳/飲料店)。"""
    places = await places_service.nearby(r, lat, lon, category, radius_meters)
    return PlaceListResponse(places=places)


@router.get("/search", response_model=PlaceListResponse)
async def search_places(
    query: Annotated[str, Query(min_length=1, max_length=64)],
    r: Annotated[redis.Redis, Depends(get_redis)],
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> PlaceListResponse:
    """文字搜尋地點 (AR 畫面搜尋框用)。"""
    places = await places_service.text_search(r, query, lat, lon)
    return PlaceListResponse(places=places)
