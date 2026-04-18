# VibeTrip Backend

> 專為 P 型旅人打造的即時盲盒行程 App — 後端服務
> FastAPI + PostgreSQL (PostGIS) + Redis

---

## 架構設計

### 資料分層 — 誰該存哪裡？

```
┌───────────────────────────────────────────────────────────────┐
│                    PostgreSQL + PostGIS                       │
│  (靜態、關聯式、需要空間查詢)                                 │
├───────────────────────────────────────────────────────────────┤
│ • 使用者帳號                                                  │
│ • 個人足跡 / 社群地標 (含 GEOGRAPHY 座標)                     │
│ • 盲盒行程模板 (TripTemplate + TripItem)                      │
│ • 公車站牌、捷運站、YouBike 站點 (位置+名稱)                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                          Redis                                │
│  (動態、秒級變動、短命快取)                                   │
├───────────────────────────────────────────────────────────────┤
│ • 公車/捷運即時到站 (TTL 15 秒)                               │
│ • YouBike 可借/可還車輛數 (TTL 30 秒)                         │
│ • 天氣資料 (TTL 10-30 分鐘)                                   │
│ • Google Places 搜尋結果 (TTL 30-60 分鐘)                     │
│ • TDX access_token (TTL 23 小時)                              │
└───────────────────────────────────────────────────────────────┘
```

**設計原則**：凡是資料在 DB 裡、需要算距離，就交給 PostGIS 一行 SQL 解決，Python 不寫距離公式。

### 目錄結構

```
app/
├── main.py                       # FastAPI 進入點
├── core/                         # 基礎建設
│   ├── config.py                 #   環境變數集中處
│   ├── database.py               #   PostgreSQL 連線
│   ├── redis_client.py           #   Redis 連線 + key 工具
│   ├── security.py               #   密碼 hash + JWT
│   └── deps.py                   #   FastAPI 依賴 (get_current_user)
├── db/
│   ├── base.py                   #   SQLAlchemy Base + mixins
│   ├── models/                   #   ORM models (全部都繼承 Base)
│   │   ├── user.py
│   │   ├── trip.py               #   TripTemplate + TripItem
│   │   ├── spot.py               #   PersonalSpot + CommunitySpot (PostGIS)
│   │   └── transit.py            #   BusStop / MrtStation / YoubikeStation (PostGIS)
│   └── init_db.py                #   建表 + seed
├── schemas/                      # Pydantic I/O schemas
├── services/                     # 業務邏輯
│   ├── auth_service.py
│   ├── trip_service.py
│   ├── weather_service.py        #   OWM + Redis 快取
│   ├── places_service.py         #   Google + Redis 快取
│   ├── transit_service.py        #   PostGIS + Redis (最典型的分工示範)
│   ├── spot_service.py           #   PostGIS 足跡
│   └── external/                 #   外部 API 薄包裝
│       ├── tdx_client.py
│       ├── owm_client.py
│       └── google_client.py
└── api/v1/endpoints/             # REST 路由
    ├── auth.py / users.py
    ├── trips.py                  #   POST /trips/recommend
    ├── weather.py                #   GET /weather/current|forecast
    ├── places.py                 #   GET /places/nearby|search
    ├── transit.py                #   GET /transit/bus/eta | /mrt/eta | /bikes
    ├── directions.py             #   POST /directions/calculate
    └── spots.py                  #   /spots/personal/* | /spots/community/*
```

API 完整規格詳見 [docs/API.md](docs/API.md)。

---

## 如何啟動

### 1. 準備 `.env`

```bash
cp .env.example .env
# 填入 TDX / OpenWeatherMap / Google API 金鑰
```

### 2. 啟動三個 service

```bash
docker compose up --build
```

第一次啟動時會：
1. 拉 postgis/redis/python image
2. 建表並 seed 26 筆盲盒行程資料
3. 啟動 API 在 `http://localhost:8000`

### 3. 開啟 Swagger

瀏覽器打開 <http://localhost:8000/docs>，可以直接試所有端點。

---

## 常見操作

### 重新建表 (清空所有資料)

```bash
docker compose down -v    # -v 會刪 volume
docker compose up --build
```

### 只重新 seed

```bash
docker compose exec api python -m app.db.init_db
```

### 看 Redis 裡有什麼

```bash
docker compose exec redis redis-cli
> KEYS vibetrip:*
> GET vibetrip:weather:current:25.03:121.56
```

### 測試 PostGIS 查詢

```bash
docker compose exec db psql -U tdx_user -d tdx_database
> SELECT name, ST_Distance(location, ST_SetSRID(ST_MakePoint(121.565, 25.033), 4326)::geography) AS d
  FROM youbike_stations
  ORDER BY d LIMIT 5;
```

---

## 開發提示

### 加新 endpoint 的流程

1. 在 `schemas/` 寫 request / response model
2. 在 `services/` 寫純業務邏輯函式 (只收 db/redis/params，回 pydantic model)
3. 在 `api/v1/endpoints/` 寫 router 端點，只負責依賴注入 + 呼叫 service
4. 在 `api/v1/api_router.py` 掛上去

### 加新的靜態資料 (例：YouBike 站點)

1. 在 `db/models/transit.py` 的 model 確認欄位
2. 寫個一次性 script 從 TDX 撈回來批次 INSERT
3. 前端查詢時自動透過 PostGIS 算距離

### 加新的動態資料快取

```python
from app.core.redis_client import build_key, cache_get_json, cache_set_json

key = build_key("my_feature", some_id)
cached = await cache_get_json(redis, key)
if cached:
    return cached
# ... 重新算
await cache_set_json(redis, key, result, ttl_seconds=60)
```

### 外部 API key 保護

所有外部 API key 只存在後端的 `.env`，前端改打我們的代理端點：

| 外部 API | 前端不再直接呼叫 → 改呼叫 |
|---|---|
| OpenWeatherMap | `/api/v1/weather/*` |
| Google Places | `/api/v1/places/*` |
| Google Directions | `/api/v1/directions/calculate` |
| TDX | `/api/v1/transit/*` |
