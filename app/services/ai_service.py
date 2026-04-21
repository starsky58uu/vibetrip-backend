import asyncio
import json

from datetime import datetime, timezone, timedelta
from math import asin, cos, radians, sin, sqrt

from groq import AsyncGroq
from app.core.config import settings
from app.core.redis_client import get_redis, build_key, cache_get_json, cache_set_json

TW_TZ = timezone(timedelta(hours=8))  # 台灣時區 UTC+8
client = AsyncGroq(api_key=settings.GROQ_API_KEY)

CACHE_TTL = 60 * 30  # 30 分鐘（含即時交通資訊，不能快取太久）

VIBE_ZH = {
    "cafe": "慵懶咖啡",
    "food": "美食探索",
    "photo": "攝影散步",
    "walk": "城市漫遊",
    "gift": "選物尋寶",
    "rain": "室內躲雨",
}

# 每種 vibe 對應的 Google Places 搜尋關鍵字（用中文，偏向台灣在地店家）
VIBE_QUERY = {
    "cafe":  "咖啡廳 獨立咖啡",
    "food":  "餐廳 小吃 美食",
    "photo": "拍照景點 網美咖啡廳 老街",
    "walk":  "公園 步道 廣場 老街",
    "gift":  "選物店 文創 手作 禮品店",
    "rain":  "書店 博物館 室內展覽 咖啡廳",
}


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine 直線距離（公里）。"""
    la1, lo1, la2, lo2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(
        sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    ))


# ─── 主入口 ────────────────────────────────────────────────────────────────────

async def generate_trip(vibe_key: str, lat: float, lon: float, weather: str | None) -> dict:
    redis = await get_redis()
    hour_slot = datetime.now(TW_TZ).hour // 2  # 每 2 小時換一個快取桶
    key = build_key("trip", "ai", vibe_key, f"{lat:.2f}", f"{lon:.2f}", hour_slot)

    cached = await cache_get_json(redis, key)
    if cached:
        return cached

    # Step 1: 先從 Google Places 查真實附近店家
    nearby = await _search_nearby(vibe_key, lat, lon)

    # Step 2: 把真實店家清單餵給 AI，讓它只負責選 + 寫描述
    result = await _call_groq(vibe_key, lat, lon, weather, nearby)

    # Step 3: 用 Google Directions 算真實步行距離
    try:
        result['items'] = await _enrich_distances(result['items'], lat, lon)
    except Exception as e:
        print(f"[MAPS WARN] 距離補正失敗: {e}", flush=True)

    await cache_set_json(redis, key, result, ttl_seconds=CACHE_TTL)
    return result


# ─── Step 1：Google Places 查附近真實店家 ─────────────────────────────────────
async def _search_nearby(vibe_key: str, lat: float, lon: float) -> list[dict]:
    from app.services.external.google_client import GoogleMapsClient

    query = VIBE_QUERY.get(vibe_key, "景點 店家")
    try:
        async with GoogleMapsClient() as gmaps:
            # 這裡不強置 opennow=True，因為公園可能沒標營業時間
            places = await gmaps.text_search(query, lat=lat, lon=lon, radius_meters=1500)
    except Exception as e:
        print(f"[PLACES WARN] 無法查詢附近店家: {e}", flush=True)
        return []

    results = []
    for p in places:
        # 1. 排除永久歇業、暫停營業 ( business_status 判斷 )
        status = p.get('business_status')
        if status and status != 'OPERATIONAL':
            continue

        loc = p.get('geometry', {}).get('location', {})
        p_lat, p_lon = loc.get('lat', 0), loc.get('lng', 0)
        dist = _dist_km(lat, lon, p_lat, p_lon)
        
        # 嚴格過濾 1.5km 直線距離
        if dist > 1.5:
            continue

        # 2. 分類處理：公園/地標 vs 一般店家
        types = p.get('types', [])
        # 判斷是否為公共景點/自然景觀
        is_landmark = any(t in types for t in ['park', 'natural_feature', 'tourist_attraction', 'church', 'museum'])
        
        rating = p.get('rating', 0)
        is_open_now = p.get('opening_hours', {}).get('open_now')

        if is_landmark:
            # 公園/景點：不強求 3.5 星，不強求營業中 (is_open_now 可能是 None)
            pass 
        else:
            # 商業店家：必須營業中 (True) 且 評分 >= 3.5
            if is_open_now is not True or rating < 3.5:
                continue

        results.append({
            'name':    p.get('name', ''),
            'address': p.get('formatted_address', ''),
            'rating':  rating,
            'types':   types
        })
            
        if len(results) >= 10:
            break
    return results

# ─── Step 2：Groq AI 生成行程 ─────────────────────────────────────────────────

async def _call_groq(
    vibe_key: str, lat: float, lon: float,
    weather: str | None, nearby: list[dict]
) -> dict:
    vibe_zh = VIBE_ZH.get(vibe_key, vibe_key)
    weather_hint = f"，今天天氣是{weather}" if weather else ""
    current_time = datetime.now(TW_TZ).strftime("%H:%M")

    # 把真實店家清單格式化成 prompt 文字
    if nearby:
        place_list = "\n".join(
            f"{i+1}. {p['name']}（評分 {p['rating']}）— {p['address']}"
            for i, p in enumerate(nearby)
        )
        places_block = f"""
【附近真實店家清單（來自 Google Maps，1.5km 以內）】
{place_list}

請從以上清單中選 3 個最符合「{vibe_zh}」氛圍的地點。
若清單不足 3 個，才可補充同區域真實存在的店家。
"""
    else:
        places_block = "請推薦使用者附近真實存在、Google 評分 3.5 以上的台灣在地店家。"

    prompt = f"""你是台灣在地旅遊達人。請為一位想要「{vibe_zh}」體驗的旅客，
在台灣（使用者目前座標：緯度 {lat:.4f}，經度 {lon:.4f}）{weather_hint}，
規劃一份 3 小時的步行行程。
{places_block}
【時間】現在是 {current_time}，第一個地點的 time 欄位填 {current_time}，之後依序累加停留時間。

請只回覆以下 JSON，不要有任何說明文字：
{{
  "title": "行程標題（10字以內，包含地區和主題）",
  "subtitle": "一句話描述氛圍（15字以內）",
  "items": [
    {{
      "time": "{current_time}",
      "dur": "60min",
      "activity": "地點名稱（直接使用清單中的名稱）",
      "desc": "一句話描述這個地點的特色和你要做什麼（25字以內）",
      "tag": "標籤（如：獨立書店、隱藏版、必吃）",
      "dist": "步行 8 分鐘",
      "mood": "一個 emoji"
    }}
  ]
}}"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "你是台灣旅遊專家，只以 JSON 格式回覆，不加任何說明文字。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ─── Step 3：距離 + 交通模式判斷 ──────────────────────────────────────────────

async def _enrich_distances(items: list[dict], user_lat: float, user_lon: float) -> list[dict]:
    from app.services.external.google_client import GoogleMapsClient

    async with GoogleMapsClient() as gmaps:
        # 1. 取得所有地點座標 (這裡要確保能精準對應到地點)
        all_places = await asyncio.gather(
            *[gmaps.text_search(item['activity'], lat=user_lat, lon=user_lon, radius_meters=2000)
              for item in items],
            return_exceptions=True,
        )

        coords = []
        for places in all_places:
            if isinstance(places, Exception) or not places:
                coords.append(None)
                continue
            loc = places[0]['geometry']['location']
            coords.append((loc['lat'], loc['lng']))

        enriched = []
        prev_lat, prev_lon = user_lat, user_lon

        for item, coord in zip(items, coords):
            # 如果抓不到座標，直接保留 AI 原文，避免報錯
            if coord is None:
                enriched.append(item)
                continue

            p_lat, p_lon = coord
            try:
                # 2. 算步行距離
                walk = await gmaps.directions(prev_lat, prev_lon, p_lat, p_lon, mode="walking")
                if walk.get('routes'):
                    leg = walk['routes'][0]['legs'][0]
                    walk_min = round(leg['duration']['value'] / 60)
                    dist_m = leg['distance']['value']
                    dist_label = f'{dist_m}m' if dist_m < 1000 else f'{dist_m / 1000:.1f}km'

                    # 3. 判斷是否需要大眾運輸 (超過 10 分鐘就查)
                    if walk_min > 10:
                        transit_str = await _check_transit(gmaps, prev_lat, prev_lon, p_lat, p_lon)
                        # 如果有大眾運輸方案，就覆蓋掉原本的 dist 欄位
                        if transit_str:
                            item['dist'] = transit_str
                        else:
                            item['dist'] = f'步行 {walk_min} 分鐘 ({dist_label})'
                    else:
                        item['dist'] = f'步行 {walk_min} 分鐘 ({dist_label})'
                else:
                    print(f"[DEBUG] 無法取得步行路徑: {item['activity']}")
            except Exception as e:
                print(f"[ERR] 距離補正失敗 {item['activity']}: {e}")

            # 更新前一個點的座標，讓下一段距離是「點到點」而不是全部「人到點」
            prev_lat, prev_lon = p_lat, p_lon
            enriched.append(item)

    return enriched