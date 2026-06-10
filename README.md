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
│   ├── health.py                 #   DB / Redis 存活檢查
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
├── services/                     # 業務邏輯（見 docs/CONVENTIONS.md）
│   ├── auth_service.py
│   ├── trip_service.py           #   盲盒推薦（AI 失敗時 fallback DB）
│   ├── ai_service.py             #   Groq + Google 行程生成
│   ├── taste_service.py          #   足跡口味分析
│   ├── weather_service.py        #   OWM + Redis 快取
│   ├── places_service.py         #   Google + Redis 快取
│   ├── transit_service.py        #   PostGIS + Redis (最典型的分工示範)
│   ├── spot_service.py           #   PostGIS 足跡
│   └── external/                 #   外部 API 薄包裝（只打 HTTP，不快取）
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

**寫 code 前請先讀** [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — 分層、命名、import、日誌、快取等統一慣例。

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

### 開發：程式風格檢查

```bash
pip install -r requirements-dev.txt
pre-commit install                             # 一次設定，之後 commit 前自動跑
pre-commit run --all-files                     # 或手動掃描
```

規則見 [docs/CONVENTIONS.md](docs/CONVENTIONS.md)。推送 PR 時 GitHub Actions 也會跑。

### 4. 透過 Cloudflare Tunnel 對外（可選）

不需開路由器 port，用 Cloudflare 把 API 公開到例如 `https://api.yourdomain.com`。

完整步驟見 **[docs/CLOUDFLARE_TUNNEL.md](docs/CLOUDFLARE_TUNNEL.md)**。摘要：

1. 在 Cloudflare Zero Trust 建立 Tunnel，複製 token 到 `.env` 的 `CLOUDFLARE_TUNNEL_TOKEN`
2. Public Hostname 指向 **`http://api:8000`**（不是 localhost）
3. 啟動：`docker compose --profile tunnel up -d`

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

## API 測試守則（重要，避免浪費 AI 額度）

### 基本觀念

後端跑起來之後**不要隨便重啟 docker**。每次 `docker compose down` 或 `docker compose restart` 都會清掉 Redis 快取，下次打 AI 就要重新消耗 Gemini/Groq 額度。

正確的測試流程：

```
docker compose up -d   ← 只啟動一次，之後保持在背景跑
     ↓
修改程式碼（docker 會自動 hot-reload，不需要重啟）
     ↓
用瀏覽器開 /docs 測試
     ↓
下班前 docker compose down（或直接讓它跑著）
```

---

### 如何用 /docs（Swagger UI）測試

1. 確認後端有在跑：瀏覽器開 `http://localhost:8000/docs`
2. 找到要測試的端點，例如 `POST /api/v1/trips/recommend`
3. 點 **Try it out**
4. 在 Request body 貼入測試資料：
   ```json
   {
     "vibe_key": "cafe",
     "latitude": 25.0330,
     "longitude": 121.5654
   }
   ```
5. 點 **Execute**
6. 看 Server response 的 Response body

---

### AI 行程端點測試守則

#### Gemini 免費額度限制

| 模型 | 每分鐘上限 | 每天上限 | 重置時間 |
|---|---|---|---|
| gemini-2.0-flash | 15 次 | 1,500 次 | 台灣時間早上 8:00 |
| gemini-2.0-flash-lite | 30 次 | 1,500 次 | 台灣時間早上 8:00 |

**每天 1,500 次聽起來很多，但：**
- 每次 debug 重打就消耗一次
- 每次 docker restart 快取清空，同樣的請求要重打
- 全部模型共用同一個 project 的配額

#### 正確測試步驟

**第一次測試（確認 AI 有接上）：**

```
1. 打一次 POST /api/v1/trips/recommend
2. 看 docker log 有沒有出現：
   → [INFO] httpx: HTTP Request: POST https://generativelanguage.googleapis.com/... "HTTP/1.1 200 OK"
   → 代表 AI 成功回應
3. 看 response body 有沒有真實地點名稱（不是「7-11」或「創意館」）
```

**確認快取有效（必做）：**

```
1. 用完全一樣的 vibe_key + latitude + longitude 再打一次
2. 看 docker log：
   → 不應該再出現 generativelanguage.googleapis.com 的 HTTP request
   → 代表第二次直接從 Redis 回傳，沒有消耗 AI 額度
3. 兩次 response 應該一模一樣
```

**查看 Redis 快取狀態：**

```bash
docker compose exec redis redis-cli
> KEYS vibetrip:trip:ai:*          # 列出所有 AI 快取的 key
> TTL vibetrip:trip:ai:cafe:25.03:121.57   # 看這筆還剩多少秒
> GET vibetrip:trip:ai:cafe:25.03:121.57   # 看快取的 JSON 內容
```

**手動清除特定快取（不要用 FLUSHALL）：**

```bash
# 只清掉 AI 行程快取，其他快取（天氣、交通）保留
docker compose exec redis redis-cli DEL vibetrip:trip:ai:cafe:25.03:121.57
```

---

### 各端點測試範例

#### 天氣（不消耗 AI 額度，可以盡量打）

```json
GET /api/v1/weather/current?lat=25.0330&lon=121.5654
```

#### AI 行程生成（節省額度：每個 vibe 只打一次）

```json
POST /api/v1/trips/recommend
{
  "vibe_key": "cafe",
  "latitude": 25.0330,
  "longitude": 121.5654
}
```

vibe_key 可選值：`cafe` / `food` / `photo` / `walk` / `gift` / `rain` / `random`

不同城市座標：
- 台北大安區：`25.0330, 121.5654`
- 台南中西區：`22.9999, 120.2269`
- 高雄鹽埕區：`22.6248, 120.2850`
- 花蓮市區：`23.9871, 121.6015`

#### 附近地點搜尋（不消耗 AI 額度）

```json
GET /api/v1/places/search?query=咖啡&lat=25.0330&lon=121.5654
```

---

### 額度用完怎麼辦

**選項 A：等到隔天早上 8:00（UTC+8）重置**

**選項 B：改用 Groq（額度更大）**

1. 去 https://console.groq.com 申請免費 key
2. 在 `.env` 加 `GROQ_API_KEY=你的key`
3. 在 `app/services/ai_service.py` 把 `genai` 換成 `AsyncGroq`
4. `docker compose up -d --build`（這次要 rebuild 因為有新套件）

Groq 免費額度：每天 14,400 次，是 Gemini 的 10 倍。

---

### 什麼時候才需要 `docker compose up -d --build`

只有以下情況才需要加 `--build`（重新打包 image）：

| 情況 | 指令 |
|---|---|
| 改了 `requirements.txt`（加新套件）| `docker compose up -d --build` |
| 第一次啟動 | `docker compose up -d --build` |
| 改了 `.env` 裡的 key | `docker compose up -d` （不需要 build）|
| 改了 Python 程式碼 | 什麼都不用做，uvicorn 自動 hot-reload |

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
