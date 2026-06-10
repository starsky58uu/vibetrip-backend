"""Google Places 搜尋與打烊時間驗證。"""

import asyncio
import logging
import random
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from app.core.redis_client import build_key, cache_get_json, cache_set_json, get_redis
from app.services.ai.constants import (
    DAY_SUPPLEMENT_QUERY,
    NIGHT_SUPPLEMENT_QUERY,
    NIGHT_TOLERANT_TYPES,
    TW_TZ,
    VIBE_QUERY,
)

logger = logging.getLogger(__name__)


def dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine 直線距離（公里）。"""
    la1, lo1, la2, lo2 = map(radians, [lat1, lon1, lat2, lon2])
    return (
        2
        * 6371
        * asin(sqrt(sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2))
    )


# ─── Step 1：Google Places 查附近真實店家 ─────────────────────────────────────


async def cached_text_search(redis, query: str, lat: float, lon: float) -> list:
    """
    帶 Redis 快取的 Google text_search — 同 query + 鄰近座標（小數點 3 位精度，
    約 110m 內視為同一格）1 小時內共用同一份結果。
    用途：
      1. 同使用者反覆搖一搖 / 重生成 → 不重複扣費
      2. 同地區多使用者搜同 vibe → 共用快取
    """
    from app.services.external.google_client import GoogleMapsClient

    key = build_key("places", "search", query, f"{lat:.3f}", f"{lon:.3f}")
    cached = await cache_get_json(redis, key)
    if cached is not None:
        return cached
    try:
        async with GoogleMapsClient() as gmaps:
            places = await gmaps.text_search(query, lat=lat, lon=lon, radius_meters=1500)
        await cache_set_json(redis, key, places, ttl_seconds=60 * 60)
        return places
    except Exception as e:
        logger.warning("Places 搜尋失敗 '%s…': %s", query[:20], e)
        return []


async def search_nearby(vibe_key: str, lat: float, lon: float) -> list[dict]:
    """
    兩段式搜尋：
      1. 用 vibe 對應關鍵字搜，依時段做過濾（深夜對便利商店/公園等放寬）
      2. 深夜且結果 < 3 筆 → 補搜「確定開著」的地點填滿清單

    回傳格式（每筆都帶 lat/lon，供 Step3 直接使用）：
      { name, address, rating, types, lat, lon }
    """
    current_hour = datetime.now(TW_TZ).hour
    is_late_night = current_hour >= 22 or current_hour < 6  # 22:00 ~ 05:59
    is_early_morning = 6 <= current_hour < 9  # 06:00 ~ 08:59

    def _passes(p: dict) -> bool:
        """單筆 Place 是否通過時段過濾。"""
        status = p.get("business_status")
        if status and status != "OPERATIONAL":
            return False  # 永久 / 暫時歇業

        rating = p.get("rating", 0)
        is_open_now = p.get("opening_hours", {}).get("open_now")
        types = p.get("types", [])
        is_landmark = any(t in types for t in ("park", "natural_feature", "tourist_attraction"))
        is_tolerant = any(t in NIGHT_TOLERANT_TYPES for t in types)

        if is_landmark:
            return True  # 開放空間不看 is_open_now
        if is_open_now is False:
            return False  # 明確關門
        # 深夜 / 清晨：沒有 is_open_now 資料的商業店家，
        # 除非屬於「大概率仍開」的類型，否則排除
        if (is_late_night or is_early_morning) and is_open_now is None and not is_tolerant:
            return False
        return rating >= 3.5

    def _extract(places: list, existing: set[str]) -> list[dict]:
        """從 Google Places 清單提取符合條件且 1.5km 以內的店家。"""
        out = []
        for p in places:
            loc = p.get("geometry", {}).get("location", {})
            p_lat, p_lon = loc.get("lat", 0), loc.get("lng", 0)
            if dist_km(lat, lon, p_lat, p_lon) > 1.5:
                continue
            if not _passes(p):
                continue
            name = p.get("name", "")
            if name in existing:
                continue
            out.append(
                {
                    "name": name,
                    "address": p.get("formatted_address", ""),
                    "rating": p.get("rating", 0),
                    "types": p.get("types", []),
                    "lat": p_lat,
                    "lon": p_lon,
                    "place_id": p.get("place_id", ""),  # 供 Place Details 查打烊時間
                }
            )
            if len(out) >= 15:  # 候選池放大：給 AI 更多選擇
                break
        return out

    # ── 第一段：vibe 多關鍵字並行搜尋（每個都走 cache）────────────────────────
    # 把 VIBE_QUERY 字串拆成多個關鍵字，隨機抽 3 個並行打。
    # 每個 (query, 鄰近座標) 結果在 Redis 快取 1h；同地區重複生成成本接近於零，
    # 又能藉「每次抽不同關鍵字」帶來真正的變化。
    redis = await get_redis()
    keywords = VIBE_QUERY.get(vibe_key, "景點 店家").split()
    chosen = random.sample(keywords, k=min(3, len(keywords)))

    raw_lists = await asyncio.gather(*[cached_text_search(redis, q, lat, lon) for q in chosen])

    results: list[dict] = []
    existing: set[str] = set()
    for raw in raw_lists:
        for p in _extract(raw, existing):
            existing.add(p["name"])
            results.append(p)

    # ── 第二段：主搜不到 3 筆 → 用通用清單補滿（也走 cache）───────────────────
    if len(results) < 3:
        main_count = len(results)
        supp_query = NIGHT_SUPPLEMENT_QUERY if is_late_night else DAY_SUPPLEMENT_QUERY
        raw_supp = await cached_text_search(redis, supp_query, lat, lon)
        supplement = _extract(raw_supp, existing)
        for p in supplement:
            if len(results) >= 15:
                break
            existing.add(p["name"])
            results.append(p)
        if supplement:
            tag = "NIGHT" if is_late_night else "DAY"
            logger.info(
                "[%s SUPPLEMENT] 主搜得 %d 筆，補充 %d 筆候選",
                tag,
                main_count,
                len(supplement),
            )

    # 打亂順序 + 上限 15：避免 AI 偏向前幾家，搖一搖 / 重生成才會有變化。
    random.shuffle(results)
    return results[:15]


# ─── Step 1b：抓打烊時間 + 過濾快關的地點 ─────────────────────────────────────


async def fetch_closing_times(nearby: list[dict]) -> None:
    """
    用 Place Details API 取得每個地點今日的打烊時間，原地寫入 nearby 清單。
    結果以 place_id + 星期 為 key 快取於 Redis（營業時間幾乎不變），
    省下重複的 Place Details API 呼叫與費用。
    closes_at 格式：
      "21:30"   → 今日 21:30 打烊
      "01:00↑"  → 次日凌晨 1:00 打烊
      "24:00"   → 24 小時
      缺欄位     → 查不到，不做限制
    """
    from app.services.external.google_client import GoogleMapsClient

    redis = await get_redis()
    now_tw = datetime.now(TW_TZ)
    # Python weekday(): 0=Mon … 6=Sun；Google Places: 0=Sun … 6=Sat
    google_today = (now_tw.weekday() + 1) % 7

    def _parse_today_close(periods: list) -> str | None:
        """從 periods 解析出「今天」的打烊時間字串，沒有則回 None。"""
        for period in periods:
            open_info = period.get("open", {})
            close_info = period.get("close")
            if open_info.get("day") != google_today:
                continue
            if close_info is None:
                return "24:00"  # 全天 24 小時
            t = close_info.get("time", "")  # "HHMM"
            if len(t) == 4:
                h, m = int(t[:2]), int(t[2:])
                next_day = close_info.get("day") != google_today
                return f"{h:02d}:{m:02d}" + ("↑" if next_day else "")
            return None
        return None

    async def _one(place: dict) -> None:
        pid = place.get("place_id", "")
        if not pid:
            return

        ckey = build_key("place", "hours", pid, google_today)
        # 先讀快取（命中就不打 API）
        cached = await cache_get_json(redis, ckey)
        if cached is not None:
            ca = cached.get("closes_at")
            if ca:
                place["closes_at"] = ca
            return

        # 快取未命中 → 打 Place Details，再回寫快取
        try:
            async with GoogleMapsClient() as gmaps:
                details = await gmaps.place_details(pid, fields="opening_hours")
            periods = details.get("opening_hours", {}).get("periods", [])
            ca = _parse_today_close(periods)
            if ca:
                place["closes_at"] = ca
            # 含 None 也快取，避免沒有營業時間資料的地點被反覆查詢；TTL 24h
            await cache_set_json(redis, ckey, {"closes_at": ca}, ttl_seconds=60 * 60 * 24)
        except Exception as e:
            logger.warning("查打烊時間失敗 %s: %s", place.get("name"), e)

    await asyncio.gather(*[_one(p) for p in nearby])


def filter_closing_soon(nearby: list[dict], min_stay_min: int = 30) -> list[dict]:
    """
    移除在「現在起 min_stay_min 分鐘內」就打烊的地點。
    （連最短的停留都排不進去的，直接砍掉，讓 AI 別排它）
    """
    now_tw = datetime.now(TW_TZ)
    now_min = now_tw.hour * 60 + now_tw.minute

    def _has_time(p: dict) -> bool:
        ca = p.get("closes_at", "")
        if not ca or ca == "24:00":
            return True  # 不知道 / 全天 → 保留
        next_day = ca.endswith("↑")
        ts = ca.rstrip("↑")
        try:
            h, m = int(ts[:2]), int(ts[3:])
        except (ValueError, IndexError):
            return True
        close_min = h * 60 + m
        if next_day or close_min < 6 * 60:
            close_min += 24 * 60  # 次日凌晨：加 24h
        remaining = close_min - now_min
        return remaining >= min_stay_min

    before = len(nearby)
    filtered = [p for p in nearby if _has_time(p)]
    removed = before - len(filtered)
    if removed:
        logger.info("移除 %d 個快打烊地點（剩餘 < %dmin）", removed, min_stay_min)
    return filtered


def validate_closing_times(items: list[dict], nearby: list[dict]) -> list[dict]:
    """
    後置驗證：用實際累計時間算出每一站的「到達時刻」，
    若到達時刻 + 停留時長 > 打烊時間，就把這一站剔除。

    時間模型：
      第 1 站到達 = 現在 + 10 分鐘（步行到第一站）
      第 N 站到達 = 前一站到達 + 前一站 dur + 10 分鐘移動
    """
    if not nearby or not items:
        return items

    # name → closes_at 查找表（_validate_activities 跑完後 activity 都是真實店名）
    closes_lookup: dict[str, str] = {p["name"]: p.get("closes_at", "") for p in nearby}

    now_tw = datetime.now(TW_TZ)
    now_min = now_tw.hour * 60 + now_tw.minute

    # 第一站到達時間：現在 + 10 分鐘
    cursor = now_min + 10

    def _parse_close_min(closes_at: str) -> int | None:
        """將 closes_at 字串轉成「今日分鐘數」，次日凌晨加 1440。"""
        if not closes_at or closes_at == "24:00":
            return None  # 全天或未知 → 不限制
        next_day = closes_at.endswith("↑")
        ts = closes_at.rstrip("↑")
        try:
            h, m = int(ts[:2]), int(ts[3:5])
        except (ValueError, IndexError):
            return None
        close_min = h * 60 + m
        if next_day or close_min < 6 * 60:
            close_min += 24 * 60  # 次日凌晨
        return close_min

    valid: list[dict] = []
    for item in items:
        activity = item.get("activity", "")
        # 解析停留時長（"60min" → 60、"45" → 45，fallback 45）
        dur_raw = item.get("dur", "45min")
        try:
            dur = int("".join(ch for ch in dur_raw if ch.isdigit())) or 45
        except Exception:
            dur = 45

        closes_at = closes_lookup.get(activity, "")
        close_min = _parse_close_min(closes_at)

        if close_min is not None:
            leave_min = cursor + dur  # 預計離開時間
            if leave_min > close_min:
                arrive_hm = f"{cursor // 60:02d}:{cursor % 60:02d}"
                leave_hm = f"{leave_min // 60 % 24:02d}:{leave_min % 60:02d}"
                logger.info(
                    "剔除 '%s'：到達 %s，停留 %dmin，離開 %s > 打烊 %s",
                    activity,
                    arrive_hm,
                    dur,
                    leave_hm,
                    closes_at,
                )
                continue  # 這一站被剔除，cursor 不往前推

        valid.append(item)
        cursor += dur + 10  # 下一站到達 = 本站離開 + 10 分鐘移動

    if len(valid) < len(items):
        logger.info("打烊驗證共剔除 %d 站", len(items) - len(valid))
    return valid
