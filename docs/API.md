# VibeTrip API 文件

> 專為 P 型旅人打造的即時盲盒行程 App — 前後端分離 API 規格書
>
> **版本**：v1 · **最後更新**：2026-04-18 · **Base URL**：`http://localhost:8000/api/v1`（開發環境）

---

## 目錄

1. [總覽](#1-總覽)
2. [通用規範](#2-通用規範)
3. [認證 Authentication](#3-認證-authentication)
4. [錯誤格式 Error Format](#4-錯誤格式)
5. [資料模型 Data Models](#5-資料模型)
6. [API 端點](#6-api-端點)
    - 6.1 [Auth 認證](#61-auth-認證)
    - 6.2 [Users 使用者](#62-users-使用者)
    - 6.3 [Trips 盲盒行程推薦](#63-trips-盲盒行程推薦)
    - 6.4 [Weather 天氣](#64-weather-天氣)
    - 6.5 [Places 地點搜尋](#65-places-地點搜尋)
    - 6.6 [Directions & Transit 路線與大眾運輸](#66-directions--transit-路線與大眾運輸)
    - 6.7 [Spots 足跡與社群地標](#67-spots-足跡與社群地標)
    - 6.8 [Uploads 圖片上傳](#68-uploads-圖片上傳)
7. [前端對應表](#7-前端對應表)
8. [快取與速率限制](#8-快取與速率限制)
9. [版本與變更紀錄](#9-版本與變更紀錄)

---

## 1. 總覽

VibeTrip 後端負責：

- **集中管理第三方 API 金鑰**（Google Maps / OpenWeatherMap / TDX），避免前端外洩。
- **聚合並快取高頻資料**（公車/捷運 ETA、YouBike 站點）以降低外部 API 呼叫次數。
- **持久化使用者資料**（帳號、個人足跡、社群地標、互動紀錄）。
- **提供盲盒行程推薦引擎**（依心情、位置、天氣產生客製化行程）。

### 技術棧

| 類別 | 技術 |
|---|---|
| Web 框架 | FastAPI 0.100+（async/await） |
| ORM | SQLAlchemy 2.0 + asyncpg |
| 地理資料 | PostgreSQL 15 + PostGIS 3.3 / GeoAlchemy2 |
| 快取 | Redis 7 |
| 認證 | JWT（python-jose）+ bcrypt（passlib） |
| 驗證 | Pydantic 2.0 |

---

## 2. 通用規範

### 2.1 URL

- **Base URL**：`{HOST}/api/v1`
- 路徑使用 **複數名詞**（`/trips`、`/spots`），資源 ID 使用 **UUID v4**。
- 查詢字串使用 `snake_case`（`?created_after=...`）。

### 2.2 Request / Response 格式

- 一律使用 `application/json`；圖片上傳使用 `multipart/form-data`。
- 所有請求與回應欄位均為 **snake_case**。
- 時間採 **ISO 8601 + UTC**（例：`2026-04-18T03:15:30Z`）。
- 座標採 **WGS84**：`latitude` ∈ [-90, 90]、`longitude` ∈ [-180, 180]。

### 2.3 Header

| Header | 必要 | 說明 |
|---|---|---|
| `Authorization` | 視端點 | `Bearer <jwt_token>` |
| `Accept-Language` | 否 | `zh-TW`（預設）/ `en` |
| `X-Client-Version` | 建議 | App 版本號，用於相容性判斷 |

### 2.4 分頁

列表型端點統一使用 cursor-based 分頁：

```
GET /spots/community?limit=20&cursor=eyJjcmVhdGVkX2F0...
```

回應：

```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "eyJjcmVhdGVkX2F0...",
    "has_more": true
  }
}
```

---

## 3. 認證 Authentication

### 3.1 機制

- 登入後取得 **access_token**（有效 1 小時）+ **refresh_token**（有效 30 天）。
- 受保護端點需帶 `Authorization: Bearer <access_token>`。
- access_token 過期時使用 `/auth/refresh` 換新。

### 3.2 公開 vs 受保護

| 類型 | 範例 |
|---|---|
| **Public**（不需登入） | `/auth/*`、`/weather/*`、`/trips/recommend`、`/places/search`、`/directions/*`、`/transit/*`、`/spots/community`（僅讀） |
| **Protected**（需登入） | `/users/me`、`/spots/personal/*`、`/spots/{id}/like`、`/spots/{id}/save`、`/uploads/*` |

前端在未登入時仍可使用盲盒、AR 導航、天氣；只有「記錄個人足跡、按讚收藏、社群發文」需登入。

---

## 4. 錯誤格式

所有錯誤統一結構：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "經緯度格式不正確",
    "details": {
      "field": "latitude",
      "constraint": "must be between -90 and 90"
    },
    "request_id": "req_01HXYZ..."
  }
}
```

### 4.1 錯誤碼

| HTTP | code | 情境 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 欄位格式錯誤 |
| 401 | `UNAUTHENTICATED` | 未帶 token 或過期 |
| 403 | `FORBIDDEN` | 無權存取該資源 |
| 404 | `NOT_FOUND` | 資源不存在 |
| 409 | `CONFLICT` | 帳號已存在、重複操作 |
| 422 | `UNPROCESSABLE` | 語義錯誤（例：座標在台灣以外） |
| 429 | `RATE_LIMITED` | 呼叫過於頻繁（含 `Retry-After` header） |
| 502 | `UPSTREAM_ERROR` | 上游 API（Google/TDX/OWM）失敗 |
| 503 | `SERVICE_UNAVAILABLE` | 維護中 |

---

## 5. 資料模型

### 5.1 User

```json
{
  "id": "uuid",
  "username": "string (3-20, 英數底線)",
  "email": "string (email)",
  "display_name": "string | null",
  "avatar_url": "string | null",
  "created_at": "datetime"
}
```

### 5.2 TripPlan

```json
{
  "id": "uuid",
  "vibe_key": "cafe | food | photo | rain | walk | gift | random",
  "title": "string",
  "generated_at": "datetime",
  "center": { "latitude": 25.033, "longitude": 121.565 },
  "items": [
    {
      "time": "14:00",
      "activity": "string",
      "desc": "string",
      "icon": "string (emoji or key)",
      "category": "cafe | restaurant | shop | park | museum | ...",
      "location": { "latitude": 25.033, "longitude": 121.565, "name": "string" } 
    }
  ],
  "estimated_duration_minutes": 180
}
```

### 5.3 PersonalSpot（個人足跡）

```json
{
  "id": "uuid",
  "owner_id": "uuid",
  "latitude": 25.033,
  "longitude": 121.565,
  "note": "string (max 500)",
  "image_url": "string | null",
  "is_public": false,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 5.4 CommunitySpot（社群地標）

```json
{
  "id": "uuid",
  "author": {
    "id": "uuid",
    "username": "string",
    "display_name": "string",
    "avatar_url": "string"
  },
  "latitude": 25.033,
  "longitude": 121.565,
  "content": "string",
  "image_url": "string | null",
  "likes_count": 42,
  "replies_count": 7,
  "created_at": "datetime",
  "viewer_state": {
    "is_liked": false,
    "is_saved": false
  }
}
```

### 5.5 Weather

```json
{
  "temperature": 22.5,
  "feels_like": 21.8,
  "condition": "Clear | Clouds | Rain | Thunderstorm | Snow | ...",
  "description": "晴",
  "icon": "01d",
  "humidity": 65,
  "wind_speed": 3.2,
  "pressure": 1013,
  "observed_at": "datetime"
}
```

### 5.6 RouteOption（AR 導航路線）

```json
{
  "mode": "walking | transit_bus | transit_mrt | youbike",
  "duration_seconds": 720,
  "distance_meters": 850,
  "available": true,
  "steps": [
    {
      "instruction": "往北步行 200 公尺到捷運中山站",
      "mode": "walking",
      "duration_seconds": 180,
      "polyline": "encoded_polyline_string"
    }
  ],
  "realtime": {
    "eta_seconds": 90,
    "vehicle_id": "TPE-1234",
    "source": "tdx"
  }
}
```

---

## 6. API 端點

### 6.1 Auth 認證

---

#### `POST /auth/register`

註冊新帳號。

**Request**

```json
{
  "username": "moxi_0508",
  "password": "Passw0rd!",
  "email": "moxi@example.com",
  "display_name": "Moxi"
}
```

**Response 201**

```json
{
  "user": { "id": "uuid", "username": "moxi_0508", "email": "...", "display_name": "Moxi", "avatar_url": null, "created_at": "..." },
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Errors**：`409 CONFLICT`（帳號/信箱已存在）、`400 VALIDATION_ERROR`（密碼強度不足）。

---

#### `POST /auth/login`

**Request**

```json
{ "username": "moxi_0508", "password": "Passw0rd!" }
```

**Response 200**：同 register 結構（不含 user 建立時間變更）。

**Errors**：`401 UNAUTHENTICATED`（帳號密碼錯誤）。

---

#### `POST /auth/refresh`

**Request**

```json
{ "refresh_token": "eyJhbGc..." }
```

**Response 200**

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600
}
```

每次 refresh 會簽發新的 refresh_token（rotation），舊 token 立即失效。

---

#### `POST /auth/logout` 🔒

撤銷當前 refresh_token。**Response 204 No Content**。

---

### 6.2 Users 使用者

---

#### `GET /users/me` 🔒

取得目前登入者資料。**Response 200**：`User` 物件。

---

#### `PATCH /users/me` 🔒

更新個人資料（部分欄位）。

**Request**

```json
{ "display_name": "Moxi 旅人", "avatar_url": "https://..." }
```

**Response 200**：更新後的 `User` 物件。

---

### 6.3 Trips 盲盒行程推薦

---

#### `POST /trips/recommend`

依心情 + 當前位置 + 天氣，產生 3 小時左右的盲盒行程。**取代前端 `mockData.js`。**

**Request**

```json
{
  "vibe_key": "cafe",
  "latitude": 25.033,
  "longitude": 121.565,
  "weather_condition": "Clear",
  "time_of_day": "afternoon",
  "exclude_trip_ids": ["uuid-1", "uuid-2"]
}
```

- `vibe_key`：`cafe | food | photo | rain | walk | gift | random`
- `weather_condition`（選填）：若提供則後端會跳過不適合的選項（例：雨天不推開放式走路行程）。
- `exclude_trip_ids`（選填）：使用者「重新搖一次」時避開剛看過的行程。

**Response 200**：`TripPlan` 物件。

**Notes**：後端需支援「搖一搖重新抽」語義 — 同樣參數多次呼叫應回傳不同結果（可用 `exclude_trip_ids` 或後端 session 紀錄）。

---

#### `GET /trips/{trip_id}`

取得某次盲盒結果（供分享、歷史查詢）。**Response 200**：`TripPlan` 物件。

**限制**：此端點僅能查詢 **DB 中的 `TripTemplate`（seed 模板）**。`POST /trips/recommend` 由 AI 即時產生的行程會回傳新的 UUID，但**不會寫入資料庫**；對這類 ID 呼叫本端點將回 **404**。若需分享 AI 行程，請在前端保存完整 `TripPlan` JSON，或等待未來的持久化 API（見 ROADMAP）。

---

### 6.4 Weather 天氣

前端目前直接呼叫 OpenWeatherMap，應全部改走後端（集中金鑰、加快取）。

---

#### `GET /weather/current`

**Query**：`lat`, `lon`

**Response 200**：`Weather` 物件 + 額外欄位：

```json
{
  "temperature": 22.5,
  "condition": "Clear",
  "description": "晴",
  "icon": "01d",
  "humidity": 65,
  "wind_speed": 3.2,
  "pressure": 1013,
  "observed_at": "2026-04-18T03:15:00Z",
  "district": "信義區",
  "greeting": "午後陽光剛剛好，出門走走吧 ☀️"
}
```

- `district`：後端反查得到的行政區（對應前端 `HomeScreen` 的「信義區」顯示）。
- `greeting`：依天氣 + 時段的招呼語（取代前端 `greetingMessage` 邏輯）。

**快取**：TTL 10 分鐘，以「座標四捨五入到小數第 2 位」為 key（同一區共用）。

---

#### `GET /weather/forecast`

**Query**：`lat`, `lon`

**Response 200**

```json
{
  "hourly": [
    { "time": "2026-04-18T06:00:00Z", "temperature": 22, "condition": "Clear", "icon": "01d", "precipitation_prob": 0.1 }
  ],
  "daily": [
    { "date": "2026-04-18", "temp_min": 18, "temp_max": 26, "condition": "Clouds", "icon": "03d", "sunrise": "05:32", "sunset": "18:14" }
  ]
}
```

**快取**：TTL 30 分鐘。

---

### 6.5 Places 地點搜尋

代理 Google Places API，支援 AR 畫面的「附近超商/咖啡/餐廳/飲料店」搜尋與文字搜尋。

---

#### `GET /places/nearby`

**Query**：

| 參數 | 型別 | 說明 |
|---|---|---|
| `lat` | float | 必填 |
| `lon` | float | 必填 |
| `category` | string | `convenience_store | cafe | restaurant | drink_shop` |
| `radius_meters` | int | 預設 500，最大 2000 |
| `limit` | int | 預設 20，最大 50 |

**Response 200**

```json
{
  "places": [
    {
      "place_id": "ChIJ...",
      "name": "全家便利商店-信義店",
      "latitude": 25.033,
      "longitude": 121.565,
      "distance_meters": 120,
      "rating": 4.3,
      "is_open_now": true,
      "categories": ["convenience_store"]
    }
  ]
}
```

---

#### `GET /places/search`

**Query**：`query`（字串）、`lat`、`lon`（可選，偏好鄰近結果）、`limit`（預設 10）。

**Response**：同 `/places/nearby`，多一個 `formatted_address` 欄位。

---

### 6.6 Directions & Transit 路線與大眾運輸

---

#### `POST /directions/calculate`

一次計算四種交通方式（步行 / 公車 / 捷運 / YouBike），**取代前端同時呼叫 Google Directions + TDX 的組合邏輯**。

**Request**

```json
{
  "origin": { "latitude": 25.033, "longitude": 121.565 },
  "destination": { "latitude": 25.047, "longitude": 121.517 },
  "modes": ["walking", "transit_bus", "transit_mrt", "youbike"],
  "departure_time": "now"
}
```

**Response 200**

```json
{
  "routes": [
    { "mode": "walking", "duration_seconds": 1800, "distance_meters": 2100, "available": true, "steps": [...] },
    { "mode": "transit_bus", "duration_seconds": 900, "distance_meters": 2100, "available": true, "steps": [...], "realtime": { "eta_seconds": 120, "vehicle_id": "..." } },
    { "mode": "transit_mrt", "duration_seconds": 600, "available": true, "steps": [...], "realtime": { "eta_seconds": 180 } },
    { "mode": "youbike", "duration_seconds": 840, "available": true, "steps": [...], "station_info": { "rent": {...}, "return": {...} } }
  ]
}
```

若某模式不可用（例：距離太近不推薦捷運、附近無 YouBike 可借），回 `available: false` + `reason`。

---

#### `GET /transit/bus/eta`

公車單一路線即時到站時間（AR 頁面開始導航後持續輪詢）。

**Query**：`route_name`（例：`207`）、`stop_name`（例：`市政府站`）、`direction`（`outbound | inbound`）。

**Response 200**

```json
{
  "route_name": "207",
  "stop_name": "市政府站",
  "eta_seconds": 90,
  "plate_number": "KKA-1234",
  "status": "approaching | in_transit | departure | no_service",
  "fetched_at": "2026-04-18T03:15:30Z"
}
```

**快取**：TTL 15 秒（配合 TDX 資料刷新頻率）。

---

#### `GET /transit/mrt/eta`

**Query**：`station_name`（例：`台北101/世貿`）、`direction`（選填）。

**Response 200**

```json
{
  "station_name": "台北101/世貿",
  "next_trains": [
    { "direction": "象山", "eta_seconds": 60 },
    { "direction": "北投", "eta_seconds": 180 }
  ],
  "fetched_at": "2026-04-18T03:15:30Z"
}
```

---

#### `GET /bikes/available`

最近可用 YouBike 站。

**Query**：`lat`、`lon`、`type`（`rent`=找車 / `return`=還車）、`limit`（預設 5）。

**Response 200**

```json
{
  "stations": [
    {
      "station_id": "500101001",
      "name": "YouBike2.0_捷運市政府站(3號出口)",
      "latitude": 25.041,
      "longitude": 121.566,
      "distance_meters": 85,
      "available_rent": 12,
      "available_return": 8,
      "bike_type": "2.0"
    }
  ]
}
```

---

### 6.7 Spots 足跡與社群地標

---

#### `POST /spots/personal` 🔒

新增個人足跡（長按地圖記錄）。

**Request**

```json
{
  "latitude": 25.033,
  "longitude": 121.565,
  "note": "今天的下午茶 ☕️",
  "image_upload_id": "uuid-from-uploads-endpoint",
  "is_public": false
}
```

- `image_upload_id`：先透過 `/uploads/images` 取得。
- `is_public: true` 則同步建立一筆 `CommunitySpot`。

**Response 201**：`PersonalSpot` 物件。

---

#### `GET /spots/personal` 🔒

列出目前使用者所有足跡。

**Query**：`limit`、`cursor`、`bbox`（選填，`min_lon,min_lat,max_lon,max_lat` 只取可視範圍）。

**Response 200**：`{ data: PersonalSpot[], pagination: {...} }`。

---

#### `PATCH /spots/personal/{spot_id}` 🔒

更新 note / image / is_public。**Response 200**：更新後的 `PersonalSpot`。

---

#### `DELETE /spots/personal/{spot_id}` 🔒

**Response 204 No Content**。

---

#### `POST /spots/personal/sync` 🔒

離線登入後批次上傳本機足跡（對應 AddSpotModal 的「同步至雲端」）。

**Request**

```json
{
  "spots": [
    { "client_id": "local-1", "latitude": 25.03, "longitude": 121.56, "note": "...", "image_upload_id": "uuid", "created_at": "2026-04-15T02:00:00Z" }
  ]
}
```

**Response 200**

```json
{
  "created": [{ "client_id": "local-1", "server_id": "uuid", "status": "created" }],
  "conflicts": []
}
```

---

#### `GET /spots/community`

取得社群地標（地圖瀏覽模式）。**無需登入即可讀取。**

**Query**：

| 參數 | 說明 |
|---|---|
| `bbox` | `min_lon,min_lat,max_lon,max_lat` 地圖可視範圍 |
| `sort` | `recent`（預設）/ `popular`（按讚數）/ `nearby`（需 `lat,lon`） |
| `lat`, `lon` | 當 `sort=nearby` 必填 |
| `limit`, `cursor` | 分頁 |

**Response 200**：`{ data: CommunitySpot[], pagination: {...} }`（含 `viewer_state`，未登入時 `is_liked/is_saved` 恆為 false）。

---

#### `GET /spots/community/{spot_id}`

單一社群地標詳情。**Response 200**：`CommunitySpot`。

---

#### `POST /spots/community/{spot_id}/like` 🔒

**Request**：空 body。

**Response 200**

```json
{ "is_liked": true, "likes_count": 43 }
```

再次呼叫即為取消讚（toggle 語義）。

---

#### `POST /spots/community/{spot_id}/save` 🔒

同 like，toggle 語義。**Response**：`{ "is_saved": true }`。

---

#### `GET /spots/community/saved` 🔒

使用者收藏清單。**Response**：`{ data: CommunitySpot[], pagination: {...} }`。

---

### 6.8 Uploads 圖片上傳

---

#### `POST /uploads/images` 🔒

上傳圖片，取得可用於 `/spots/personal` 的 `upload_id`。

**Request**：`multipart/form-data`
- `file`：jpeg / png / webp，最大 10 MB。
- `purpose`：`spot_image | avatar`

**Response 201**

```json
{
  "upload_id": "uuid",
  "url": "https://cdn.vibetrip.tw/spots/uuid.jpg",
  "width": 1080,
  "height": 1080,
  "expires_at": "2026-04-18T04:15:00Z"
}
```

- `upload_id` 未綁定到資源者，`expires_at` 之後會被清除。
- 後端需做：格式驗證、EXIF 去除、自動壓縮、生成縮圖。

---

## 7. 前端對應表

以下列出前端現有資料來源與 API 端點的對應，前端重構時直接替換。

| 功能 | 前端檔案 | 目前資料來源 | 取代為 |
|---|---|---|---|
| 盲盒行程 | [useBlindBoxLogic.js](src/screens/BlindBox/hooks/useBlindBoxLogic.js) | `mockData.js` 硬編碼 | `POST /trips/recommend` |
| 首頁天氣 | [useHomeData.js](src/screens/Home/hooks/useHomeData.js) | OpenWeatherMap（直呼） | `GET /weather/current` |
| 天氣詳情 | [useWeatherForecast.js](src/screens/Weather/hooks/useWeatherForecast.js) | OpenWeatherMap（直呼） | `GET /weather/forecast` |
| AR 地點搜尋 | [useArLogic.js](src/screens/AR/hooks/useArLogic.js) `performSearch` | Google Places（直呼） | `GET /places/nearby` + `/places/search` |
| AR 路線規劃 | [useArLogic.js](src/screens/AR/hooks/useArLogic.js) `onSelectCandidate` | Google Directions + TDX（直呼） | `POST /directions/calculate` |
| 公車 ETA | [useArLogic.js](src/screens/AR/hooks/useArLogic.js) | TDX（直呼） | `GET /transit/bus/eta` |
| 捷運 ETA | useArLogic + `mrt_map.json` | TDX（直呼） | `GET /transit/mrt/eta`（後端自行維護站點對照） |
| YouBike | useArLogic | TDX（直呼） | `GET /bikes/available` |
| 個人足跡 | [useMapLogic.js](src/screens/Map/hooks/useMapLogic.js) | 本機 state | `/spots/personal/*` + `/spots/personal/sync` |
| 社群地標 | [mapData.js](src/screens/Map/constants/mapData.js) `DUMMY_COMMUNITY_SPOTS` | 硬編碼 | `GET /spots/community` |
| 登入 | [LoginModal.jsx](src/screens/Map/components/LoginModal.jsx) | `setTimeout` 假裝登入 | `POST /auth/login` + `/auth/register` |
| 圖片上傳 | AddSpotModal（尚未實作） | — | `POST /uploads/images` |

### 前端改動重點

1. **新增 `src/api/` 目錄**，封裝所有 HTTP 呼叫（建議用 axios + interceptor 處理 token refresh）。
2. **新增 `AuthContext`**，管理 access_token / refresh_token 與當前使用者；`MapScreen` 的 `isLoggedIn` 改讀 context。
3. **從 `app.config.js` 移除** `EXPO_PUBLIC_GOOGLE_API_KEY`（地圖 rendering 仍需，但 Places/Directions/TDX 全部改走後端）、`EXPO_PUBLIC_TDX_*`、`EXPO_PUBLIC_OPENWEATHER_API_KEY`。
4. **新增 `EXPO_PUBLIC_API_BASE_URL`**，分 dev / staging / prod。

---

## 8. 快取與速率限制

### 8.1 後端 Redis 快取策略

| 端點 | Key | TTL |
|---|---|---|
| `/weather/current` | `weather:current:{lat_r2}:{lon_r2}` | 10 分鐘 |
| `/weather/forecast` | `weather:forecast:{lat_r2}:{lon_r2}` | 30 分鐘 |
| `/places/nearby` | `places:nearby:{lat_r3}:{lon_r3}:{category}:{radius}` | 1 小時 |
| `/places/search` | `places:search:{query}:{lat_r2}:{lon_r2}` | 30 分鐘 |
| `/directions/calculate` | `dir:{origin}:{dest}:{modes}` | 5 分鐘（含即時資訊者不快取 steps） |
| `/transit/bus/eta` | `bus:{route}:{stop}:{dir}` | 15 秒 |
| `/transit/mrt/eta` | `mrt:{station}` | 15 秒 |
| `/bikes/available` | `bikes:{lat_r3}:{lon_r3}:{type}` | 30 秒 |

> `lat_r2` = 經緯度四捨五入到小數第 2 位；`lat_r3` = 第 3 位（約 100m 精度）。

### 8.2 速率限制（per user / per IP）

| 範圍 | 限制 |
|---|---|
| 未登入 IP | 60 req / 分鐘 |
| 登入使用者 | 300 req / 分鐘 |
| `/auth/login`、`/auth/register` | 10 req / 分鐘 / IP（防暴力破解） |
| `/uploads/images` | 30 req / 小時 / user |

超限回 `429 RATE_LIMITED` 並帶 `Retry-After` header。

---

## 9. 版本與變更紀錄

### v1.0.0 · 2026-04-18（初版）

- 定義完整 v1 API：Auth、Users、Trips、Weather、Places、Directions/Transit、Spots、Uploads。
- 納入目前前端 6 個畫面 + 6 個 hooks 的完整需求。

### 後續規劃（v1.1+）

- [ ] WebSocket `/ws/transit/live`：AR 導航改推送替代輪詢。
- [ ] `/trips/history`：使用者盲盒紀錄、最愛行程。
- [ ] `/spots/community/{id}/replies`：社群地標留言串。
- [ ] 第三方登入（Google / Apple）。
- [ ] 多語系 i18n（目前 `Accept-Language` 已保留）。

---

## 附錄 A · 後端實作建議順序

建議依以下順序落地（每階段結束前端都可替換對應模組）：

1. **Phase 1 — 基礎**：資料庫 schema + User model + `/auth/*` + `/users/me`。
2. **Phase 2 — 第三方代理**：`/weather/*` + `/places/*` + `/transit/*` + `/bikes/*`（只做代理與快取，不需 DB）。這階段完成後前端 AR/首頁/天氣可完全不直呼外部 API。
3. **Phase 3 — 推薦引擎**：`/trips/recommend` + `/trips/{id}`。先從 `mockData.js` 搬資料進 DB，再加上心情 × 天氣 × 時段的規則。
4. **Phase 4 — 使用者內容**：`/uploads/images` + `/spots/personal/*` + `/spots/community/*`。
5. **Phase 5 — 進階**：`/directions/calculate`（整合 Google Directions + TDX 路線）、速率限制、監控。

## 附錄 B · 範例 cURL

```bash
# 註冊
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"moxi","password":"Passw0rd!","email":"m@x.com"}'

# 盲盒
curl -X POST http://localhost:8000/api/v1/trips/recommend \
  -H "Content-Type: application/json" \
  -d '{"vibe_key":"cafe","latitude":25.033,"longitude":121.565}'

# 帶 token 新增足跡
curl -X POST http://localhost:8000/api/v1/spots/personal \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"latitude":25.033,"longitude":121.565,"note":"下午茶"}'
```
