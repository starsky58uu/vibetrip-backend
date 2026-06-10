"""步行距離與大眾運輸建議補全。"""

import asyncio
import logging
from datetime import datetime

from app.services.ai.constants import TW_TZ
from app.services.ai.places import dist_km

logger = logging.getLogger(__name__)


# ─── Step 3：距離 + 交通模式判斷 ──────────────────────────────────────────────


def match_coord(activity: str, nearby_cache: list[dict]) -> tuple[float, float] | None:
    """
    從 Step1 的快取清單中找出 activity 對應的座標。
    先試精確比對，再試部分包含比對，都找不到回 None（才去重查 Google）。
    """
    # 精確比對
    for p in nearby_cache:
        if p["name"] == activity:
            return (p["lat"], p["lon"])
    # 部分包含比對（AI 可能縮寫或加括號）
    for p in nearby_cache:
        if p["name"] in activity or activity in p["name"]:
            return (p["lat"], p["lon"])
    return None


async def enrich_distances(
    items: list[dict],
    user_lat: float,
    user_lon: float,
    nearby_cache: list[dict] | None = None,
) -> list[dict]:
    """
    為每個行程項目補上真實步行距離。

    優先從 nearby_cache（Step1 結果）取座標，省去重複 API 呼叫。
    只有 cache miss 時才呼叫 Google Places text_search。
    """
    from app.services.external.google_client import GoogleMapsClient

    async with GoogleMapsClient() as gmaps:
        # ── 取得每個地點的座標 ───────────────────────────────────────────────
        coords: list[tuple[float, float] | None] = []
        search_tasks = []
        search_indices = []

        for i, item in enumerate(items):
            coord = match_coord(item["activity"], nearby_cache or [])
            if coord:
                coords.append(coord)
            else:
                # Cache miss：標記位置，之後批次查詢
                coords.append(None)
                search_tasks.append(
                    gmaps.text_search(
                        item["activity"], lat=user_lat, lon=user_lon, radius_meters=2000
                    )
                )
                search_indices.append(i)

        # 批次執行所有 cache miss 的 Google 搜尋
        if search_tasks:
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            for list_i, result in zip(search_indices, search_results, strict=True):
                if isinstance(result, Exception) or not result:
                    continue
                loc = result[0]["geometry"]["location"]
                p_lat, p_lon = loc["lat"], loc["lng"]
                if dist_km(user_lat, user_lon, p_lat, p_lon) <= 5.0:
                    coords[list_i] = (p_lat, p_lon)

        # ── 算路線（各段並行）──────────────────────────────────────────────────
        # 每一段的「起點」在座標解析完後就已確定（前一個有座標的地點，或使用者位置），
        # 不需互相等待 → 全部並行，行程生成快好幾秒。
        legs: list[
            tuple[int, float, float, float, float]
        ] = []  # (item_idx, fromLat, fromLon, toLat, toLon)
        prev_lat, prev_lon = user_lat, user_lon
        for i, coord in enumerate(coords):
            if coord is not None:
                legs.append((i, prev_lat, prev_lon, coord[0], coord[1]))
                prev_lat, prev_lon = coord

        async def _one_leg(
            from_lat: float, from_lon: float, to_lat: float, to_lon: float
        ) -> str | None:
            try:
                walk = await gmaps.directions(from_lat, from_lon, to_lat, to_lon, mode="walking")
                if not walk.get("routes"):
                    return None
                leg = walk["routes"][0]["legs"][0]
                walk_min = round(leg["duration"]["value"] / 60)
                dist_m = leg["distance"]["value"]
                dist_lbl = f"{dist_m}m" if dist_m < 1000 else f"{dist_m / 1000:.1f}km"
                if walk_min > 10:
                    transit_str = await check_transit(gmaps, from_lat, from_lon, to_lat, to_lon)
                    return transit_str or f"步行 {walk_min} 分鐘 ({dist_lbl})"
                return f"步行 {walk_min} 分鐘 ({dist_lbl})"
            except Exception:
                return None

        leg_results = await asyncio.gather(
            *[_one_leg(fl, fo, tl, to) for (_idx, fl, fo, tl, to) in legs]
        )
        for (idx, *_rest), dist in zip(legs, leg_results, strict=True):
            if dist:
                items[idx]["dist"] = dist

    return items


async def check_transit(
    gmaps,
    prev_lat: float,
    prev_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> str | None:
    """
    查現在出發能否搭大眾運輸：
    - 走到站 ≤ 10 分鐘
    - 下一班等候 ≤ 30 分鐘
    符合條件回傳格式化字串，否則回 None（降回步行）。
    """
    now_ts = int(datetime.now(TW_TZ).timestamp())
    try:
        route = await gmaps.directions(
            prev_lat,
            prev_lon,
            dest_lat,
            dest_lon,
            mode="transit",
            departure_time=now_ts,
        )
    except Exception:
        return None

    if not route.get("routes"):
        return None

    leg = route["routes"][0]["legs"][0]
    steps = leg.get("steps", [])

    walk_to_stop_sec = 0
    first_transit = None
    for step in steps:
        if step.get("travel_mode") == "WALKING" and first_transit is None:
            walk_to_stop_sec += step["duration"]["value"]
        elif step.get("travel_mode") == "TRANSIT":
            first_transit = step
            break

    if first_transit is None or walk_to_stop_sec > 10 * 60:
        return None

    td = first_transit.get("transit_details", {})
    dep_ts = td.get("departure_time", {}).get("value")
    if dep_ts is None:
        return None

    wait_min = round((dep_ts - now_ts) / 60)
    if wait_min < 0 or wait_min > 30:
        return None

    total_min = round(leg["duration"]["value"] / 60)
    line = td.get("line", {})
    vehicle_type = line.get("vehicle", {}).get("type", "")
    line_name = line.get("short_name") or line.get("name", "")

    if "SUBWAY" in vehicle_type or "HEAVY_RAIL" in vehicle_type:
        mode_label = f"搭捷運{line_name}"
    elif "BUS" in vehicle_type:
        mode_label = f"搭公車{line_name}"
    else:
        mode_label = f"搭{line_name}" if line_name else "搭大眾運輸"

    return f"{mode_label} 約{total_min}分鐘（{wait_min}分後有班）"
