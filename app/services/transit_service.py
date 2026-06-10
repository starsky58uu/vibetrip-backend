"""
大眾運輸服務層 — 這是 PostgreSQL + Redis 分工最漂亮的地方。

分工：
┌──────────────────────┬─────────────┬──────────────────────────┐
│ 資料                 │ 存哪裡      │ 為什麼                   │
├──────────────────────┼─────────────┼──────────────────────────┤
│ 站牌名稱/座標        │ PostgreSQL  │ 幾乎不變，PostGIS 算距離 │
│ 路線經過哪些站       │ PostgreSQL  │ 靜態關聯                 │
│ 公車現在離幾分鐘     │ Redis       │ 15 秒就變                │
│ YouBike 可借/可還數  │ Redis       │ 秒級變動                 │
│ TDX access_token     │ Redis       │ 跨 worker 共用           │
└──────────────────────┴─────────────┴──────────────────────────┘
"""

from datetime import UTC, datetime

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import build_key, cache_get_json, cache_set_json
from app.db.models.transit import MrtStation
from app.schemas.transit import (
    BusEtaResponse,
    BusStatus,
    MrtEtaResponse,
    MrtTrainInfo,
    YoubikeStationResponse,
)
from app.services.external.tdx_client import TDXClient

BUS_ETA_TTL = 15  # 秒，配合 TDX 更新頻率
MRT_ETA_TTL = 15
YOUBIKE_STATUS_TTL = 30  # 秒


# ==========================================================================
# 公車 ETA
# ==========================================================================
async def get_bus_eta(
    r: redis.Redis,
    route_name: str,
    stop_name: str,
    city: str = "Taipei",
) -> BusEtaResponse:
    """查某條路線在某站的即時到站 (有 15 秒 Redis 快取)。"""

    key = build_key("bus", city, route_name, stop_name)
    cached = await cache_get_json(r, key)
    if cached:
        return BusEtaResponse.model_validate(cached)

    async with TDXClient() as tdx:
        raw = await tdx.get_bus_eta(city, route_name, stop_name)

    result = _parse_bus_eta(raw, route_name, stop_name)
    await cache_set_json(r, key, result.model_dump(mode="json"), ttl_seconds=BUS_ETA_TTL)
    return result


def _parse_bus_eta(raw: dict | None, route: str, stop: str) -> BusEtaResponse:
    """把 TDX 格式轉成我們的 schema。"""
    if raw is None:
        return BusEtaResponse(
            route_name=route,
            stop_name=stop,
            eta_seconds=None,
            plate_number=None,
            status="no_service",
            fetched_at=datetime.now(UTC),
        )

    # TDX StopStatus: 0=正常, 1=尚未發車, 2=交管不停靠, 3=末班駛離, 4=排班...
    stop_status = raw.get("StopStatus", 0)
    eta_seconds = raw.get("EstimateTime")

    status: BusStatus
    if stop_status in (1, 3, 4):
        status = "no_service"
        eta_seconds = None
    elif eta_seconds is None:
        status = "no_service"
    elif eta_seconds <= 30:
        status = "departure"
    elif eta_seconds <= 60:
        status = "approaching"
    else:
        status = "in_transit"

    return BusEtaResponse(
        route_name=route,
        stop_name=stop,
        eta_seconds=eta_seconds,
        plate_number=raw.get("PlateNumb"),
        status=status,
        fetched_at=datetime.now(UTC),
    )


# ==========================================================================
# 捷運 ETA
# ==========================================================================
async def get_mrt_eta(r: redis.Redis, db: AsyncSession, station_name: str) -> MrtEtaResponse:
    """查捷運某站的即時到站。"""

    key = build_key("mrt", station_name)
    cached = await cache_get_json(r, key)
    if cached:
        return MrtEtaResponse.model_validate(cached)

    # 先用 name → 查 DB 拿 station_id (TDX API 需要 station_id)
    stmt = MrtStation.__table__.select().where(MrtStation.name == station_name).limit(1)
    row = (await db.execute(stmt)).first()
    if row is None:
        return MrtEtaResponse(
            station_name=station_name,
            next_trains=[],
            fetched_at=datetime.now(UTC),
        )

    station_id = row.tdx_station_id

    async with TDXClient() as tdx:
        raw_list = await tdx.get_mrt_eta(station_id)

    trains = [
        MrtTrainInfo(
            direction=item.get("TripHeadSign", ""),
            eta_seconds=int(item["EstimateTime"]) if item.get("EstimateTime") is not None else None,
        )
        for item in raw_list
    ]

    result = MrtEtaResponse(
        station_name=station_name,
        next_trains=trains,
        fetched_at=datetime.now(UTC),
    )
    await cache_set_json(r, key, result.model_dump(mode="json"), ttl_seconds=MRT_ETA_TTL)
    return result


# ==========================================================================
# YouBike — PostGIS + Redis 結合的範例
# ==========================================================================
async def nearest_youbike(
    r: redis.Redis,
    db: AsyncSession,
    lat: float,
    lon: float,
    return_type: str,  # "rent" (找車) / "return" (還車)
    limit: int = 5,
) -> list[YoubikeStationResponse]:
    """
    找最近的 N 個 YouBike 站。

    步驟：
    1. 用 PostGIS 找出座標最近的 N 站 → 拿到 station_id 們 (靜態資料)
    2. 從 Redis 批次拿這些 station_id 的可借/可還數量 (動態資料)
    3. 如果 Redis 沒有 → 去 TDX 撈整批、塞回 Redis
    4. 組合回傳
    """

    # ---------- (1) PostGIS 找最近 ----------
    # 解釋這段 SQL：
    # - ST_MakePoint(lon, lat) 做出使用者當前位置
    # - ST_DWithin(..., 3000) 先用 3 公里圓圈過濾 (會吃 GIST 索引，非常快)
    # - ST_Distance(...) 用 geography 算出真實公尺距離
    # - <-> 是 PostGIS 的 KNN 操作符，依距離排序時超快
    stmt = text(
        """
            SELECT id, tdx_station_id, name, bike_type, address,
                   ST_Y(location::geometry) AS lat,
                   ST_X(location::geometry) AS lon,
                   ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
            FROM youbike_stations
            WHERE ST_DWithin(
                location,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                3000
            )
            ORDER BY distance_m
            LIMIT :limit
            """
    )
    rows = (await db.execute(stmt, {"lat": lat, "lon": lon, "limit": limit * 2})).mappings().all()

    if not rows:
        return []

    # ---------- (2) Redis 拿動態車輛數 ----------
    status_map = await _load_youbike_status(r)

    results: list[YoubikeStationResponse] = []
    for row in rows:
        status = status_map.get(row["tdx_station_id"], {"available_rent": 0, "available_return": 0})

        # 根據使用者意圖過濾沒車/沒位的站
        if return_type == "rent" and status["available_rent"] == 0:
            continue
        if return_type == "return" and status["available_return"] == 0:
            continue

        results.append(
            YoubikeStationResponse(
                station_id=row["tdx_station_id"],
                name=row["name"],
                latitude=row["lat"],
                longitude=row["lon"],
                distance_meters=round(row["distance_m"], 1),
                available_rent=status["available_rent"],
                available_return=status["available_return"],
                bike_type=row["bike_type"],
            )
        )
        if len(results) >= limit:
            break

    return results


async def _load_youbike_status(r: redis.Redis) -> dict[str, dict]:
    """
    把整個城市的 YouBike 即時狀態做成 { station_id: {rent, return} } dict。
    30 秒內重複使用 Redis 快取的版本。
    """
    key = build_key("youbike", "status", "Taipei")
    cached = await cache_get_json(r, key)
    if cached:
        return cached

    async with TDXClient() as tdx:
        raw = await tdx.get_youbike_stations_status("Taipei")

    # TDX 欄位：StationID / AvailableRentBikes / AvailableReturnBikes
    mapping = {
        item["StationID"]: {
            "available_rent": item.get("AvailableRentBikes", 0),
            "available_return": item.get("AvailableReturnBikes", 0),
        }
        for item in raw
    }

    await cache_set_json(r, key, mapping, ttl_seconds=YOUBIKE_STATUS_TTL)
    return mapping


# ==========================================================================
# 公車站最近查詢 (給 directions 用)
# ==========================================================================
async def nearest_bus_stops(
    db: AsyncSession,
    lat: float,
    lon: float,
    limit: int = 3,
) -> list[dict]:
    """PostGIS 找最近公車站 — 純靜態查詢，不需 Redis。"""
    stmt = text(
        """
        SELECT tdx_stop_id, name, route_names,
               ST_Y(location::geometry) AS lat,
               ST_X(location::geometry) AS lon,
               ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
        FROM bus_stops
        ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
        LIMIT :limit
        """
    )
    rows = (await db.execute(stmt, {"lat": lat, "lon": lon, "limit": limit})).mappings().all()
    return [dict(r) for r in rows]


async def nearest_mrt_stations(
    db: AsyncSession,
    lat: float,
    lon: float,
    limit: int = 3,
) -> list[dict]:
    """PostGIS 找最近捷運站。"""
    stmt = text(
        """
        SELECT tdx_station_id, name, line_code,
               ST_Y(location::geometry) AS lat,
               ST_X(location::geometry) AS lon,
               ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
        FROM mrt_stations
        ORDER BY location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
        LIMIT :limit
        """
    )
    rows = (await db.execute(stmt, {"lat": lat, "lon": lon, "limit": limit})).mappings().all()
    return [dict(r) for r in rows]
