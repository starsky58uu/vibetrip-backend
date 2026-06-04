import asyncio
import json
import random

from datetime import datetime, timezone, timedelta
from math import asin, cos, radians, sin, sqrt
from uuid import UUID

from groq import AsyncGroq
from app.core.config import settings
from app.core.redis_client import get_redis, build_key, cache_get_json, cache_set_json

TW_TZ = timezone(timedelta(hours=8))
client = AsyncGroq(api_key=settings.GROQ_API_KEY)

CACHE_TTL = 60 * 30  # 30 分鐘

VIBE_ZH = {
    "cafe": "慵懶咖啡",
    "food": "美食探索",
    "photo": "攝影散步",
    "walk": "城市漫遊",
    "gift": "選物尋寶",
    "rain": "室內躲雨",
}

VIBE_QUERY = {
    "cafe":  "咖啡廳 獨立咖啡 書店 文創小店 公園 文創市集",
    "food":  "餐廳 小吃 台灣美食 美食 麵包店 手搖飲 甜點 飲料店",
    "photo": "拍照景點 網美咖啡廳 老街 公園 文創市集 網美景點",
    "walk":  "公園 步道 老街 飲料店 咖啡廳 便利商店 手搖飲",
    "gift":  "選物店 文創 手作 禮品店 文創市集 市集 特色小店 服飾店 雜貨店 書店 唱片行",
    "rain":  "書店 博物館 室內展覽 咖啡廳 購物商場 百貨",
}

# ── 每種 vibe 的人性化行程組成規則（餵給 AI，避免全程都是同類地點）──────────────
VIBE_COMPOSITION_RULE = {
    "cafe": (
        "【行程組成規則】最多安排 1~2 間咖啡廳（各 45~60 分鐘），"
        "其餘穿插：逛書店、在公園發呆、逛文創小店、買手搖飲邊走邊喝（10~15 分鐘）。"
        "手搖飲或咖啡請選擇在附近走路10分鐘內可以到的。"
        "節奏要有張有弛：坐夠了就走走，走累了再找地方坐。"
        "不要讓整個行程都是在不同咖啡廳之間移動。"
    ),
    "food": (
        "【行程組成規則】只安排 1 間主食正餐（60~90 分鐘）。"
        "其餘選：甜點店（20~30 分鐘）、手搖飲攤（10~15 分鐘）、"
        "吃完後散步消化（20~30 分鐘，desc 寫「漫步消化，感受街區氛圍」之類的話）、"
        "逛傳統市場或老街（30~45 分鐘）。"
        "嚴禁：吃完正餐後馬上接另一家正餐，或整個行程都在吃主食。"
    ),
    "walk": (
        "【行程組成規則】行程必須前往 3～4 個不同的地點，絕對不可以全程只待在同一個公園或廣場。"
        "建議結構：先去一個主要景點（公園/老街/廣場，30～45 分鐘）→"
        "走累了找一間飲料店或便利商店買杯飲料（10～15 分鐘，選清單中真實的店名）→"
        "飲料店或便利商店請選擇在附近走路10分鐘內可以到的。"
        "再去另一個不同的地點繼續探索（公園、書店、小店、廣場，30～40 分鐘）→"
        "最後找一間小咖啡廳或甜點店坐下休息（30～45 分鐘）。"
        "每個 item 都必須是不同的地點，不能重複列同一個地名超過 1 次。"
    ),
    "photo": (
        "【行程組成規則】2~3 個主要拍照景點（各 30~45 分鐘），景點間穿插："
        "買咖啡或手搖飲邊走邊喝（10~15 分鐘）、找個角落坐下等光線（15~20 分鐘）、"
        "逛附近文創小店或老屋（20~30 分鐘）。"
        "手搖飲或咖啡請選擇在附近走路10分鐘內可以到的。"
    ),
    "gift": (
        "【行程組成規則】2~3 間選物店或文創市集（各 30~45 分鐘），中間穿插："
        "買杯手搖飲或咖啡（10~15 分鐘）、找地方坐下休息喘口氣（15~20 分鐘）。"
        "逛完選物可以在附近找個小吃或飲料收尾。"
        "手搖飲或咖啡請選擇在附近走路10分鐘內可以到的。"
    ),
    "rain": (
        "【行程組成規則】行程必須前往 2～3 個不同的室內地點，不可以全程只待在同一棟建築裡。"
        "可選的室內類型：書店（30～45 分鐘）、博物館/展覽（45～60 分鐘）、"
        "購物商場或百貨地下美食街（30～45 分鐘）、咖啡廳（45 分鐘）、電影院（120 分鐘）。"
        "建議結構範例：書店逛逛 → 附近咖啡廳喝咖啡躲雨 → 購物商場隨意逛逛等雨停。"
        "建議結構範例：電影院看電影 → 休息一下 → 購物商場逛逛。"
        "每個 item 都是不同的室內場所，地點間移動 dist 標注「帶傘步行 X 分鐘」。"
    ),
}


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine 直線距離（公里）。"""
    la1, lo1, la2, lo2 = map(radians, [lat1, lon1, lat2, lon2])
    return 2 * 6371 * asin(sqrt(
        sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    ))


# ─── 主入口 ────────────────────────────────────────────────────────────────────

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
      3. Google Directions 算真實步行距離（優先用 Step1 快取座標，避免重複呼叫）

    exclude_trip_ids 非空時跳過快取讀取，確保搖一搖每次都有新結果。
    """
    redis = await get_redis()
    now_for_key = datetime.now(TW_TZ)
    # 深夜（22~05）每小時換一個 slot，日間每 2 小時一個 slot
    h = now_for_key.hour
    hour_slot = h if (h >= 22 or h < 6) else h // 2
    key = build_key("trip", "ai", vibe_key, f"{lat:.2f}", f"{lon:.2f}", hour_slot)

    # 只有沒有 exclude 時才嘗試讀快取（搖一搖要繞過快取拿新行程）
    use_cache = not exclude_trip_ids
    if use_cache:
        cached = await cache_get_json(redis, key)
        if cached:
            return cached

    # Step 1：Google Places 查真實附近店家（回傳含 lat/lon）
    nearby = await _search_nearby(vibe_key, lat, lon)

    # Step 1b：17:00 後才需要算打烊時間（白天基本不會遇到問題）
    if nearby and datetime.now(TW_TZ).hour >= 17:
        await _fetch_closing_times(nearby)
        # 只移除「現在已關或 15 分鐘內就關」的地點（連第一站都來不及）
        # 剩下的打烊資訊交由 AI prompt + 後置驗證處理
        nearby = _filter_closing_soon(nearby, min_stay_min=15)

    # Step 2：AI 選地點 + 寫描述
    result = await _call_groq(vibe_key, lat, lon, weather, nearby)

    # Step 2b：防幻覺 — 確保 activity 名稱都是 Google Places 真實存在的店
    if nearby and result.get('items'):
        result['items'] = _validate_activities(result['items'], nearby)

    # Step 2c：後置打烊驗證 — 計算每站實際到達時間，剔除會關門的站
    if nearby and result.get('items'):
        result['items'] = _validate_closing_times(result['items'], nearby)

    # Step 3：用 Step1 快取座標算距離，找不到才重查 Google
    try:
        result['items'] = await _enrich_distances(result['items'], lat, lon, nearby)
    except Exception as e:
        print(f"[MAPS WARN] 距離補正失敗: {e}", flush=True)

    # 無論有無 exclude，都把新結果存入快取供下次一般瀏覽使用
    await cache_set_json(redis, key, result, ttl_seconds=CACHE_TTL)
    return result


# ─── Step 1：Google Places 查附近真實店家 ─────────────────────────────────────

# 深夜：即使 Google 沒有 is_open_now 資料，這些 Place type 通常仍開著
_NIGHT_TOLERANT_TYPES = frozenset({
    'convenience_store',  # 7-11、全家幾乎全天 24h
    'park',               # 公園全天開放
    'natural_feature',    # 自然景點
    'tourist_attraction', # 觀光景點多為全天
    'bar',                # 酒吧通常深夜開
    'night_club',         # 夜店
})

# 結果不足時用的通用補充清單
_NIGHT_SUPPLEMENT_QUERY = "居酒屋 酒吧 漫畫咖啡廳 宵夜小吃 鹹酥雞 24小時便利商店 夜間公園"
_DAY_SUPPLEMENT_QUERY   = "咖啡廳 餐廳 景點 公園 書店 甜點 文創"


async def _cached_text_search(redis, query: str, lat: float, lon: float) -> list:
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
        print(f"[PLACES WARN] '{query[:20]}…': {e}", flush=True)
        return []


async def _search_nearby(vibe_key: str, lat: float, lon: float) -> list[dict]:
    """
    兩段式搜尋：
      1. 用 vibe 對應關鍵字搜，依時段做過濾（深夜對便利商店/公園等放寬）
      2. 深夜且結果 < 3 筆 → 補搜「確定開著」的地點填滿清單

    回傳格式（每筆都帶 lat/lon，供 Step3 直接使用）：
      { name, address, rating, types, lat, lon }
    """
    from app.services.external.google_client import GoogleMapsClient

    current_hour  = datetime.now(TW_TZ).hour
    is_late_night    = current_hour >= 22 or current_hour < 6   # 22:00 ~ 05:59
    is_early_morning = 6 <= current_hour < 9                    # 06:00 ~ 08:59

    def _passes(p: dict) -> bool:
        """單筆 Place 是否通過時段過濾。"""
        status = p.get('business_status')
        if status and status != 'OPERATIONAL':
            return False                          # 永久 / 暫時歇業

        rating      = p.get('rating', 0)
        is_open_now = p.get('opening_hours', {}).get('open_now')
        types       = p.get('types', [])
        is_landmark = any(t in types for t in ('park', 'natural_feature', 'tourist_attraction'))
        is_tolerant = any(t in _NIGHT_TOLERANT_TYPES for t in types)

        if is_landmark:
            return True                           # 開放空間不看 is_open_now
        if is_open_now is False:
            return False                          # 明確關門
        # 深夜 / 清晨：沒有 is_open_now 資料的商業店家，
        # 除非屬於「大概率仍開」的類型，否則排除
        if (is_late_night or is_early_morning) and is_open_now is None and not is_tolerant:
            return False
        return rating >= 3.5

    def _extract(places: list, existing: set[str]) -> list[dict]:
        """從 Google Places 清單提取符合條件且 1.5km 以內的店家。"""
        out = []
        for p in places:
            loc = p.get('geometry', {}).get('location', {})
            p_lat, p_lon = loc.get('lat', 0), loc.get('lng', 0)
            if _dist_km(lat, lon, p_lat, p_lon) > 1.5:
                continue
            if not _passes(p):
                continue
            name = p.get('name', '')
            if name in existing:
                continue
            out.append({
                'name':     name,
                'address':  p.get('formatted_address', ''),
                'rating':   p.get('rating', 0),
                'types':    p.get('types', []),
                'lat':      p_lat,
                'lon':      p_lon,
                'place_id': p.get('place_id', ''),   # 供 Place Details 查打烊時間
            })
            if len(out) >= 15:                 # 候選池放大：給 AI 更多選擇
                break
        return out

    # ── 第一段：vibe 多關鍵字並行搜尋（每個都走 cache）────────────────────────
    # 把 VIBE_QUERY 字串拆成多個關鍵字，隨機抽 3 個並行打。
    # 每個 (query, 鄰近座標) 結果在 Redis 快取 1h；同地區重複生成成本接近於零，
    # 又能藉「每次抽不同關鍵字」帶來真正的變化。
    redis = await get_redis()
    keywords = VIBE_QUERY.get(vibe_key, "景點 店家").split()
    chosen   = random.sample(keywords, k=min(3, len(keywords)))

    raw_lists = await asyncio.gather(*[
        _cached_text_search(redis, q, lat, lon) for q in chosen
    ])

    results:  list[dict] = []
    existing: set[str]   = set()
    for raw in raw_lists:
        for p in _extract(raw, existing):
            existing.add(p['name'])
            results.append(p)

    # ── 第二段：主搜不到 3 筆 → 用通用清單補滿（也走 cache）───────────────────
    if len(results) < 3:
        main_count = len(results)
        supp_query = _NIGHT_SUPPLEMENT_QUERY if is_late_night else _DAY_SUPPLEMENT_QUERY
        raw_supp   = await _cached_text_search(redis, supp_query, lat, lon)
        supplement = _extract(raw_supp, existing)
        for p in supplement:
            if len(results) >= 15:
                break
            existing.add(p['name'])
            results.append(p)
        if supplement:
            tag = "NIGHT" if is_late_night else "DAY"
            print(
                f"[{tag} SUPPLEMENT] 主搜得 {main_count} 筆，"
                f"補充 {len(supplement)} 筆候選",
                flush=True,
            )

    # 打亂順序 + 上限 15：避免 AI 偏向前幾家，搖一搖 / 重生成才會有變化。
    random.shuffle(results)
    return results[:15]


# ─── Step 1b：抓打烊時間 + 過濾快關的地點 ─────────────────────────────────────

async def _fetch_closing_times(nearby: list[dict]) -> None:
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
            open_info  = period.get('open', {})
            close_info = period.get('close')
            if open_info.get('day') != google_today:
                continue
            if close_info is None:
                return '24:00'                       # 全天 24 小時
            t = close_info.get('time', '')           # "HHMM"
            if len(t) == 4:
                h, m = int(t[:2]), int(t[2:])
                next_day = close_info.get('day') != google_today
                return f"{h:02d}:{m:02d}" + ('↑' if next_day else '')
            return None
        return None

    async def _one(place: dict) -> None:
        pid = place.get('place_id', '')
        if not pid:
            return

        ckey = build_key("place", "hours", pid, google_today)
        # 先讀快取（命中就不打 API）
        cached = await cache_get_json(redis, ckey)
        if cached is not None:
            ca = cached.get('closes_at')
            if ca:
                place['closes_at'] = ca
            return

        # 快取未命中 → 打 Place Details，再回寫快取
        try:
            async with GoogleMapsClient() as gmaps:
                details = await gmaps.place_details(pid, fields="opening_hours")
            periods = details.get('opening_hours', {}).get('periods', [])
            ca = _parse_today_close(periods)
            if ca:
                place['closes_at'] = ca
            # 含 None 也快取，避免沒有營業時間資料的地點被反覆查詢；TTL 24h
            await cache_set_json(redis, ckey, {'closes_at': ca}, ttl_seconds=60 * 60 * 24)
        except Exception as e:
            print(f"[CLOSE TIME WARN] {place.get('name')}: {e}", flush=True)

    await asyncio.gather(*[_one(p) for p in nearby])


def _filter_closing_soon(nearby: list[dict], min_stay_min: int = 30) -> list[dict]:
    """
    移除在「現在起 min_stay_min 分鐘內」就打烊的地點。
    （連最短的停留都排不進去的，直接砍掉，讓 AI 別排它）
    """
    now_tw  = datetime.now(TW_TZ)
    now_min = now_tw.hour * 60 + now_tw.minute

    def _has_time(p: dict) -> bool:
        ca = p.get('closes_at', '')
        if not ca or ca == '24:00':
            return True           # 不知道 / 全天 → 保留
        next_day = ca.endswith('↑')
        ts = ca.rstrip('↑')
        try:
            h, m = int(ts[:2]), int(ts[3:])
        except (ValueError, IndexError):
            return True
        close_min = h * 60 + m
        if next_day or close_min < 6 * 60:
            close_min += 24 * 60  # 次日凌晨：加 24h
        remaining = close_min - now_min
        return remaining >= min_stay_min

    before  = len(nearby)
    filtered = [p for p in nearby if _has_time(p)]
    removed  = before - len(filtered)
    if removed:
        print(f"[CLOSING SOON] 移除 {removed} 個快打烊地點（剩餘 < {min_stay_min}min）", flush=True)
    return filtered


def _validate_closing_times(items: list[dict], nearby: list[dict]) -> list[dict]:
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
    closes_lookup: dict[str, str] = {p['name']: p.get('closes_at', '') for p in nearby}

    now_tw  = datetime.now(TW_TZ)
    now_min = now_tw.hour * 60 + now_tw.minute

    # 第一站到達時間：現在 + 10 分鐘
    cursor = now_min + 10

    def _parse_close_min(closes_at: str) -> int | None:
        """將 closes_at 字串轉成「今日分鐘數」，次日凌晨加 1440。"""
        if not closes_at or closes_at == '24:00':
            return None          # 全天或未知 → 不限制
        next_day = closes_at.endswith('↑')
        ts = closes_at.rstrip('↑')
        try:
            h, m = int(ts[:2]), int(ts[3:5])
        except (ValueError, IndexError):
            return None
        close_min = h * 60 + m
        if next_day or close_min < 6 * 60:
            close_min += 24 * 60   # 次日凌晨
        return close_min

    valid: list[dict] = []
    for item in items:
        activity = item.get('activity', '')
        # 解析停留時長（"60min" → 60、"45" → 45，fallback 45）
        dur_raw = item.get('dur', '45min')
        try:
            dur = int(''.join(ch for ch in dur_raw if ch.isdigit())) or 45
        except Exception:
            dur = 45

        closes_at = closes_lookup.get(activity, '')
        close_min = _parse_close_min(closes_at)

        if close_min is not None:
            leave_min = cursor + dur           # 預計離開時間
            if leave_min > close_min:
                arrive_hm = f"{cursor // 60:02d}:{cursor % 60:02d}"
                leave_hm  = f"{leave_min // 60 % 24:02d}:{leave_min % 60:02d}"
                print(
                    f"[CLOSING VALIDATE] 剔除 '{activity}'："
                    f"預計到達 {arrive_hm}，停留 {dur}min，"
                    f"離開 {leave_hm} > 打烊 {closes_at}",
                    flush=True,
                )
                continue    # 這一站被剔除，cursor 不往前推

        valid.append(item)
        cursor += dur + 10   # 下一站到達 = 本站離開 + 10 分鐘移動

    if len(valid) < len(items):
        print(
            f"[CLOSING VALIDATE] 共剔除 {len(items) - len(valid)} 站（會超過打烊時間）",
            flush=True,
        )
    return valid


# ─── Step 2：Groq AI 生成行程 ─────────────────────────────────────────────────

def _slot_time_hint(now_tw: datetime) -> str:
    """
    計算行程各站的預估到達時刻字串，餵給 AI 做打烊檢查參考。
    假設第一站 10 分鐘後到，每站停留 45 分鐘 + 10 分鐘移動。
    """
    cursor = now_tw.hour * 60 + now_tw.minute + 10
    lines = []
    for i in range(5):
        hh = (cursor // 60) % 24
        mm = cursor % 60
        lines.append(f"  第{i + 1}站：約 {hh:02d}:{mm:02d}")
        cursor += 45 + 10
    return "\n".join(lines)


async def _call_groq(
    vibe_key: str, lat: float, lon: float,
    weather: str | None, nearby: list[dict]
) -> dict:
    vibe_zh = VIBE_ZH.get(vibe_key, vibe_key)
    weather_hint = f"，今天天氣是{weather}" if weather else ""
    now_tw = datetime.now(TW_TZ)
    current_time = now_tw.strftime("%H:%M")
    hour = now_tw.hour

    # ── 時段限制（細分深夜 / 凌晨 / 清晨）──────────────────────────────────────
    if hour >= 22 or hour < 3:
        # 深夜 22:00～02:59
        time_constraint = (
            "\n【深夜行程規則 ⚠️】現在是深夜，行程只需 2～3 個地點。"
            "主力推薦：居酒屋、餐酒館、酒吧、漫畫咖啡廳（24小時）、"
            "宵夜小吃（鹹酥雞攤、深夜拉麵、牛肉麵湯）、KTV、夜間景觀台、夜間開放公園。"
            "嚴禁：以麥當勞或速食店當主要地點（便利商店只能是「順路買杯咖啡」的過渡點）；"
            "嚴禁推薦夕陽、日落、日出相關活動；嚴禁推薦一般日間咖啡廳或商店。"
            "最後一個地點要能讓人待到凌晨（酒吧、居酒屋、漫畫咖啡廳均可）。"
        )
    elif hour < 6:
        # 凌晨 03:00～05:59
        time_constraint = (
            "\n【凌晨行程規則 ⚠️】現在是凌晨，行程只需 2～3 個地點，節奏輕鬆。"
            "適合推薦：傳統批發市場（部分 04:00 起開始進貨）、"
            "24 小時便利商店（買消夜、補充能量）、"
            "夜間開放公園或河濱步道（吹風看星星）、凌晨仍有宵夜攤的地點、夜間景觀台。"
            "嚴禁推薦夕陽、日落、一般日間才開的商家。"
        )
    elif hour < 9:
        # 清晨 06:00～08:59
        time_constraint = (
            "\n【清晨行程規則 ⚠️】現在是清晨，行程 2～3 個地點，節奏輕鬆不要塞太滿。"
            "適合推薦：傳統早市、晨間公園（太極/慢跑/散步）、早餐店、早開咖啡廳、河濱晨騎路線。"
            "便利商店可以是買早餐的選項之一，但不能是行程唯一亮點。"
            "嚴禁推薦需要等到中午才開的店家或夜間才有的活動。"
        )
    else:
        time_constraint = ""

    # ── 每種 vibe 的人性化行程組成規則 ──────────────────────────────────────────
    composition_rule = VIBE_COMPOSITION_RULE.get(vibe_key, "")

    if nearby:
        def _fmt_place(i: int, p: dict) -> str:
            ca = p.get('closes_at', '')
            if ca == '24:00':
                close_tag = '，24小時'
            elif ca:
                # "21:30" → 打烊 21:30；"01:00↑" → 打烊 01:00(次日)
                close_tag = f"，打烊 {ca.replace('↑', '(次日)')}"
            else:
                close_tag = ''
            return f"{i+1}. {p['name']}（評分 {p['rating']}{close_tag}）— {p['address']}"

        place_list = "\n".join(_fmt_place(i, p) for i, p in enumerate(nearby))
        places_block = f"""
【附近真實店家清單（來自 Google Maps，1.5km 以內）】
{place_list}

⚠️ 絕對規則（違反即為錯誤輸出）：
- activity 欄位必須逐字使用上方清單中的完整店名，一個字都不能改
- 嚴禁自行創造、捏造、縮寫或翻譯任何店名
- 每個地點在行程中只能出現 1 次（不要重複同一個地名）
- 若清單地點數量不足以安排 3～4 個不同地點，寧可縮短行程（只排 2 個地點），也不要重複同一個地點
- 「散步消化」「休息一下」「買杯飲料」等過渡活動，activity 欄位也必須選清單中一個真實地點（例如選公園名或飲料店名），用 desc 說明你要做什麼
- 有「打烊」時間的地點，必須確認：該地點的到達時間（前面所有 dur 累加）＋ 本站 dur ≤ 打烊時間，否則不要安排或提前排入行程
- 快打烊的地點（剩餘時間少）要優先排在行程前面
"""
    else:
        # nearby 完全空（例如：深夜找不到任何開著的店）
        if hour >= 22 or hour < 3:
            places_block = (
                "現在是深夜，附近商家幾乎都已打烊。"
                "請推薦此時段確實開放、人可以去的地方（只需 2～3 個地點），例如：\n"
                "・居酒屋、餐酒館、酒吧（深夜的靈魂地點）\n"
                "・漫畫咖啡廳（24小時，可以待到天亮）\n"
                "・鹹酥雞攤、深夜拉麵、牛肉麵湯等宵夜小吃\n"
                "・KTV、夜間景觀台\n"
                "・夜間開放公園或河濱步道（作為散步過渡）\n"
                "嚴禁以麥當勞作為主要地點。請選使用者座標附近真實存在的地點，不要捏造店名。"
            )
        elif hour < 6:
            places_block = (
                "現在是凌晨，大多數商家都已打烊。只需 2～3 個地點，例如：\n"
                "・24 小時便利商店（買消夜、補充能量）\n"
                "・夜間開放公園或河濱步道（吹風看星星）\n"
                "・傳統批發市場（部分清晨 04:00 起開始進貨，可去感受氣氛）\n"
                "請選使用者座標附近真實存在的地點，不要捏造店名。"
            )
        elif hour < 9:
            places_block = (
                "現在是清晨，請推薦清晨開放的場所，"
                "例如：早餐店、晨間公園、傳統市場、早開咖啡廳等。"
                "請選使用者座標附近真實存在的地點。"
            )
        else:
            places_block = "請推薦使用者附近真實存在、Google 評分 3.5 以上的台灣在地店家。"

    prompt = f"""你是台灣在地旅遊達人，深知台灣人的生活節奏與真實喜好。
請為一位想要「{vibe_zh}」體驗的旅客，
在台灣（使用者目前座標：緯度 {lat:.4f}，經度 {lon:.4f}）{weather_hint}，
規劃一份人性化的步行行程。{time_constraint}

{composition_rule}

{places_block}

【停留時間參考 — dur 欄位必須符合這個邏輯】
- 正餐（餐廳/小吃店）：60～90min
- 咖啡廳：45～60min
- 甜點店、手搖飲攤：10～20min（不要給 60min！）
- 散步、漫步消化、公園休息：20～30min
- 書店、選物店、逛街：30～45min
- 景點拍照：30～45min
- 酒吧、居酒屋、漫畫咖啡廳：60～90min

【時間】現在是 {current_time}。
各站預估到達時刻（每站平均45分鐘 + 移動10分鐘）：
{_slot_time_hint(now_tw)}
⚠️ 有打烊時間的地點，「預估到達時刻 ＋ 本站 dur」必須 ≤ 打烊時間，否則絕對不能排入行程。
第一個地點 time 填 {current_time}，之後根據前一個地點 dur 累加計算。

請只回覆以下 JSON，不要有任何說明文字：
{{
  "title": "行程標題（10字以內，包含地區和主題）",
  "subtitle": "一句話描述氛圍（15字以內）",
  "items": [
    {{
      "time": "{current_time}",
      "dur": "60min",
      "activity": "清單中的完整地點名稱（不縮寫；散步/休息/買飲料也要填真實地點名，例如「大安森林公園」不要填「在附近散步」）",
      "desc": "一句話說明在這個地點要做什麼、有什麼特色（25字以內，例如：「吃完飯在這裡漫步消化，感受午後老街氛圍」）",
      "tag": "標籤（2～5字，如：散步消化、隱藏版甜點、宵夜必去、書香下午）",
      "dist": "步行 X 分鐘",
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
        temperature=0.75,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ─── Step 2b：防幻覺驗證 ──────────────────────────────────────────────────────

def _validate_activities(items: list[dict], nearby: list[dict]) -> list[dict]:
    """
    確保 AI 回傳的每個 activity 名稱確實存在於 nearby 清單中、
    且每個地點在同一份行程內不重複出現。
    觸發替換的情況：
      1. AI 編造不在清單的地點
      2. AI 把同一家真實店名連續排了好幾站（會把第 2 次以後改成別家）
    替換邏輯：優先選「尚未使用」的最高評分地點；
    所有地點都已使用過時，依「使用次數最少 → 評分最高」排序取替補。
    """
    if not nearby:
        return items

    def find_real_name(activity: str) -> str | None:
        # 1. 完全相符
        for p in nearby:
            if p['name'] == activity:
                return p['name']
        # 2. 部分包含（AI 可能縮寫或加括號）
        for p in nearby:
            if p['name'] in activity or activity in p['name']:
                return p['name']
        return None

    validated = []
    # 統計每個地點已被用幾次，用來決定備選順序
    use_count: dict[str, int] = {p['name']: 0 for p in nearby}

    for item in items:
        real = find_real_name(item.get('activity', ''))
        used_names = {v['activity'] for v in validated}

        # 真名存在「且」尚未在本趟用過 → 直接收下
        if real and real not in used_names:
            use_count[real] = use_count.get(real, 0) + 1
            validated.append({**item, 'activity': real})
            continue

        # 否則：AI 編造不在清單、或重複選同一家 → 換成未使用的最高評分地點
        by_rating = sorted(nearby, key=lambda x: -x.get('rating', 0))
        fallback_place = next(
            (p for p in by_rating if p['name'] not in used_names),
            None,
        )
        if fallback_place is None:
            # nearby 已全數用過（候選清單比行程站數少）→ 寧可少一站也不重複
            print(
                f"[VALIDATE DROP] '{item.get('activity')}' "
                f"附近候選清單已用完，從行程移除此站",
                flush=True,
            )
            continue

        use_count[fallback_place['name']] = use_count.get(fallback_place['name'], 0) + 1
        reason = '已重複' if real else '不在清單'
        print(
            f"[VALIDATE FIX] '{item.get('activity')}' ({reason}) "
            f"→ 替換為 '{fallback_place['name']}'",
            flush=True,
        )
        validated.append({**item, 'activity': fallback_place['name']})

    return validated


# ─── Step 3：距離 + 交通模式判斷 ──────────────────────────────────────────────

def _match_coord(activity: str, nearby_cache: list[dict]) -> tuple[float, float] | None:
    """
    從 Step1 的快取清單中找出 activity 對應的座標。
    先試精確比對，再試部分包含比對，都找不到回 None（才去重查 Google）。
    """
    # 精確比對
    for p in nearby_cache:
        if p['name'] == activity:
            return (p['lat'], p['lon'])
    # 部分包含比對（AI 可能縮寫或加括號）
    for p in nearby_cache:
        if p['name'] in activity or activity in p['name']:
            return (p['lat'], p['lon'])
    return None


async def _enrich_distances(
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
            coord = _match_coord(item['activity'], nearby_cache or [])
            if coord:
                coords.append(coord)
            else:
                # Cache miss：標記位置，之後批次查詢
                coords.append(None)
                search_tasks.append(
                    gmaps.text_search(item['activity'], lat=user_lat, lon=user_lon, radius_meters=2000)
                )
                search_indices.append(i)

        # 批次執行所有 cache miss 的 Google 搜尋
        if search_tasks:
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            for list_i, result in zip(search_indices, search_results):
                if isinstance(result, Exception) or not result:
                    continue
                loc = result[0]['geometry']['location']
                p_lat, p_lon = loc['lat'], loc['lng']
                if _dist_km(user_lat, user_lon, p_lat, p_lon) <= 5.0:
                    coords[list_i] = (p_lat, p_lon)

        # ── 算路線（各段並行）──────────────────────────────────────────────────
        # 每一段的「起點」在座標解析完後就已確定（前一個有座標的地點，或使用者位置），
        # 不需互相等待 → 全部並行，行程生成快好幾秒。
        legs: list[tuple[int, float, float, float, float]] = []  # (item_idx, fromLat, fromLon, toLat, toLon)
        prev_lat, prev_lon = user_lat, user_lon
        for i, coord in enumerate(coords):
            if coord is not None:
                legs.append((i, prev_lat, prev_lon, coord[0], coord[1]))
                prev_lat, prev_lon = coord

        async def _one_leg(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> str | None:
            try:
                walk = await gmaps.directions(from_lat, from_lon, to_lat, to_lon, mode="walking")
                if not walk.get('routes'):
                    return None
                leg = walk['routes'][0]['legs'][0]
                walk_min = round(leg['duration']['value'] / 60)
                dist_m   = leg['distance']['value']
                dist_lbl = f'{dist_m}m' if dist_m < 1000 else f'{dist_m / 1000:.1f}km'
                if walk_min > 10:
                    transit_str = await _check_transit(gmaps, from_lat, from_lon, to_lat, to_lon)
                    return transit_str or f'步行 {walk_min} 分鐘 ({dist_lbl})'
                return f'步行 {walk_min} 分鐘 ({dist_lbl})'
            except Exception:
                return None

        leg_results = await asyncio.gather(
            *[_one_leg(fl, fo, tl, to) for (_idx, fl, fo, tl, to) in legs]
        )
        for (idx, *_rest), dist in zip(legs, leg_results):
            if dist:
                items[idx]['dist'] = dist

    return items


async def _check_transit(
    gmaps,
    prev_lat: float, prev_lon: float,
    dest_lat: float, dest_lon: float,
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
            prev_lat, prev_lon, dest_lat, dest_lon,
            mode="transit", departure_time=now_ts,
        )
    except Exception:
        return None

    if not route.get('routes'):
        return None

    leg   = route['routes'][0]['legs'][0]
    steps = leg.get('steps', [])

    walk_to_stop_sec = 0
    first_transit    = None
    for step in steps:
        if step.get('travel_mode') == 'WALKING' and first_transit is None:
            walk_to_stop_sec += step['duration']['value']
        elif step.get('travel_mode') == 'TRANSIT':
            first_transit = step
            break

    if first_transit is None or walk_to_stop_sec > 10 * 60:
        return None

    td     = first_transit.get('transit_details', {})
    dep_ts = td.get('departure_time', {}).get('value')
    if dep_ts is None:
        return None

    wait_min = round((dep_ts - now_ts) / 60)
    if wait_min < 0 or wait_min > 30:
        return None

    total_min    = round(leg['duration']['value'] / 60)
    line         = td.get('line', {})
    vehicle_type = line.get('vehicle', {}).get('type', '')
    line_name    = line.get('short_name') or line.get('name', '')

    if 'SUBWAY' in vehicle_type or 'HEAVY_RAIL' in vehicle_type:
        mode_label = f'搭捷運{line_name}'
    elif 'BUS' in vehicle_type:
        mode_label = f'搭公車{line_name}'
    else:
        mode_label = f'搭{line_name}' if line_name else '搭大眾運輸'

    return f'{mode_label} 約{total_min}分鐘（{wait_min}分後有班）'
