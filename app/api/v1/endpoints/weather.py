"""天氣端點 — 代理 OpenWeatherMap，加上 Redis 快取。"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query

from app.core.redis_client import get_redis
from app.schemas.weather import CurrentWeatherResponse, ForecastResponse
from app.services import weather_service

router = APIRouter()


@router.get("/current", response_model=CurrentWeatherResponse)
async def current_weather(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    r: Annotated[redis.Redis, Depends(get_redis)],
) -> CurrentWeatherResponse:
    """取當前天氣 (10 分鐘快取)。"""
    return await weather_service.get_current(r, lat, lon)


@router.get("/forecast", response_model=ForecastResponse)
async def forecast(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    r: Annotated[redis.Redis, Depends(get_redis)],
) -> ForecastResponse:
    """5 日預報 (30 分鐘快取)。"""
    return await weather_service.get_forecast(r, lat, lon)
