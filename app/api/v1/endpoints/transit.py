"""公車 / 捷運即時到站 + YouBike 端點。"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas.transit import BusEtaResponse, MrtEtaResponse, YoubikeListResponse
from app.services import transit_service

router = APIRouter()


# ---------- 公車 ----------
@router.get("/bus/eta", response_model=BusEtaResponse)
async def bus_eta(
    route_name: Annotated[str, Query(max_length=16)],
    stop_name: Annotated[str, Query(max_length=64)],
    r: Annotated[redis.Redis, Depends(get_redis)],
    city: str = "Taipei",
) -> BusEtaResponse:
    """某路線在某站的即時到站時間 (15 秒快取)。"""
    return await transit_service.get_bus_eta(r, route_name, stop_name, city)


# ---------- 捷運 ----------
@router.get("/mrt/eta", response_model=MrtEtaResponse)
async def mrt_eta(
    station_name: Annotated[str, Query(max_length=64)],
    r: Annotated[redis.Redis, Depends(get_redis)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MrtEtaResponse:
    """捷運某站各方向的到站時間。"""
    return await transit_service.get_mrt_eta(r, db, station_name)


# ---------- YouBike ----------
@router.get("/bikes", response_model=YoubikeListResponse)
async def nearby_bikes(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    type: Annotated[Literal["rent", "return"], Query()],
    r: Annotated[redis.Redis, Depends(get_redis)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> YoubikeListResponse:
    """
    找最近的 N 個 YouBike 站。
    type=rent 回傳「有車可借」的站、type=return 回傳「有位可還」的站。
    """
    stations = await transit_service.nearest_youbike(r, db, lat, lon, type, limit)
    return YoubikeListResponse(stations=stations)
