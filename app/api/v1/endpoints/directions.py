"""
路線規劃端點 — 整合 Google Directions + 我們自家的 PostGIS + Redis。

前端只打一次，就能同時拿到步行、公車、捷運、YouBike 四種路線選項。
比起前端自己去拼 Google + TDX，乾淨很多。
"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas.transit import (
    DirectionsRequest,
    DirectionsResponse,
    RouteOption,
    RouteStep,
)
from app.services import transit_service
from app.services.external.google_client import GoogleMapsClient

router = APIRouter()


@router.get("/raw", summary="原始 Google Directions 路線（供 AR 逐步導航）")
async def raw_directions(
    olat: Annotated[float, Query(ge=-90, le=90)],
    olng: Annotated[float, Query(ge=-180, le=180)],
    dlat: Annotated[float, Query(ge=-90, le=90)],
    dlng: Annotated[float, Query(ge=-180, le=180)],
    mode: str = "walking",
) -> dict:
    """
    代理 Google Directions，回傳完整原始路線（含 steps / maneuver /
    end_location / distance），讓前端 AR 逐步導航沿用原本的解析邏輯，
    且金鑰只留在後端，不外流到 App。
    """
    async with GoogleMapsClient() as g:
        raw = await g.directions(olat, olng, dlat, dlng, mode=mode)
    routes = raw.get("routes", [])
    return {"routes": routes[:1]}  # 只回第一條，保持與 Google 原始結構相容


@router.post("/calculate", response_model=DirectionsResponse)
async def calculate(
    req: DirectionsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    r: Annotated[redis.Redis, Depends(get_redis)],
) -> DirectionsResponse:
    """
    計算從 A 到 B 的所有路線選項。

    流程：
    1. walking → 直接問 Google Directions
    2. transit_bus / transit_mrt → Google Directions 的 transit 模式
    3. youbike → 用 PostGIS 找起點/終點附近各自最近的 YouBike 站 + Redis 看有沒有車
    """
    routes: list[RouteOption] = []

    async with GoogleMapsClient() as g:
        # ----- 步行 -----
        if "walking" in req.modes:
            routes.append(await _google_route(g, req, mode="walking", our_mode="walking"))

        # ----- 公車/捷運 (共用 Google transit 模式) -----
        if "transit_bus" in req.modes or "transit_mrt" in req.modes:
            transit_route = await _google_route(g, req, mode="transit", our_mode="transit_bus")
            if "transit_bus" in req.modes:
                routes.append(transit_route)
            if "transit_mrt" in req.modes:
                routes.append(transit_route.model_copy(update={"mode": "transit_mrt"}))

    # ----- YouBike -----
    if "youbike" in req.modes:
        routes.append(await _youbike_route(db, r, req))

    return DirectionsResponse(routes=routes)


async def _google_route(
    g: GoogleMapsClient,
    req: DirectionsRequest,
    mode: str,
    our_mode: str,
) -> RouteOption:
    """把 Google Directions 的回應整理成我們的 RouteOption。"""
    raw = await g.directions(
        req.origin_latitude,
        req.origin_longitude,
        req.destination_latitude,
        req.destination_longitude,
        mode=mode,
    )

    routes = raw.get("routes", [])
    if not routes:
        return RouteOption(
            mode=our_mode,  # type: ignore
            duration_seconds=0,
            distance_meters=0,
            available=False,
            reason="Google Directions 沒有可用路線",
        )

    leg = routes[0]["legs"][0]
    steps = [
        RouteStep(
            instruction=s.get("html_instructions", "").replace("<b>", "").replace("</b>", ""),
            mode=our_mode,  # type: ignore
            duration_seconds=s.get("duration", {}).get("value", 0),
        )
        for s in leg.get("steps", [])
    ]

    return RouteOption(
        mode=our_mode,  # type: ignore
        duration_seconds=leg.get("duration", {}).get("value", 0),
        distance_meters=leg.get("distance", {}).get("value", 0),
        available=True,
        steps=steps,
    )


async def _youbike_route(
    db: AsyncSession,
    r: redis.Redis,
    req: DirectionsRequest,
) -> RouteOption:
    """
    YouBike 路線 = 起點找車 + 騎車 + 終點還車。

    這是 PostGIS + Redis 完美合作的範例：
    - PostGIS 負責「從全部 YouBike 站中挑最近的」
    - Redis 負責「這些站現在還有沒有車/位」
    """

    # 起點附近「可借車」的站
    rent_stations = await transit_service.nearest_youbike(
        r,
        db,
        req.origin_latitude,
        req.origin_longitude,
        "rent",
        limit=1,
    )
    # 終點附近「可還車」的站
    return_stations = await transit_service.nearest_youbike(
        r,
        db,
        req.destination_latitude,
        req.destination_longitude,
        "return",
        limit=1,
    )

    if not rent_stations:
        return RouteOption(
            mode="youbike",
            duration_seconds=0,
            distance_meters=0,
            available=False,
            reason="附近沒有可借的 YouBike",
        )
    if not return_stations:
        return RouteOption(
            mode="youbike",
            duration_seconds=0,
            distance_meters=0,
            available=False,
            reason="終點附近沒有可還車位",
        )

    rent = rent_stations[0]
    ret = return_stations[0]

    # 簡化估算：走到站 + 騎車 + 走到目的地
    # 速度假設：走路 1.2 m/s、腳踏車 4 m/s
    walk_to_rent_seconds = int(rent.distance_meters / 1.2)
    walk_from_return_seconds = int(ret.distance_meters / 1.2)

    # 兩 YouBike 站之間的直線距離粗估 (想精準就改打一次 Google bicycling mode)
    dlat = req.destination_latitude - req.origin_latitude
    dlon = req.destination_longitude - req.origin_longitude
    ride_meters = int(((dlat**2 + dlon**2) ** 0.5) * 111_000)
    ride_seconds = int(ride_meters / 4)

    return RouteOption(
        mode="youbike",
        duration_seconds=walk_to_rent_seconds + ride_seconds + walk_from_return_seconds,
        distance_meters=ride_meters,
        available=True,
        steps=[
            RouteStep(
                instruction=f"步行 {rent.distance_meters:.0f}m 到 {rent.name}",
                mode="walking",
                duration_seconds=walk_to_rent_seconds,
            ),
            RouteStep(
                instruction=f"騎 YouBike 前往 {ret.name}",
                mode="youbike",
                duration_seconds=ride_seconds,
            ),
            RouteStep(
                instruction=f"還車後步行 {ret.distance_meters:.0f}m 到目的地",
                mode="walking",
                duration_seconds=walk_from_return_seconds,
            ),
        ],
    )
