# 同一台機器：開發 + 正式並存

適合：**你的電腦同時當 prod server（Cloudflare Tunnel）和本機開發環境**。

## 架構

```
                    Internet
                        │
                        ▼
              Cloudflare Tunnel
                        │
                        ▼
              api :8000  ←── .env（DEBUG=false，正式）
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
        db            redis      uploads volume
         ▲              ▲
         │              │
    api-dev :8001  ←── .env + .env.development（DEBUG=true，熱重載）
         │
    本機 Expo / 瀏覽器 http://localhost:8001
```

- **Prod**（`:8000` → tunnel → `https://vibetrip.codingraccoon.com`）：一直跑，給 App 使用者
- **Dev**（`:8001`）：你要改 code 時才開，不影響 tunnel
- **DB / Redis**：共用同一組 volume（dev 改 schema 會影響 prod 資料，solo 開發可接受）

## 第一次設定

```bash
cd vibetrip-backend
cp .env.development.example .env.development
```

`.env` = 正式（已有 DEBUG=false、tunnel token 等）。  
`.env.development` = 只放 dev 覆寫（DEBUG、CORS、限流等）。

前端（`vibetrip/`）：

```bash
cp .env.local.example .env.local
# 把 EXPO_PUBLIC_API_BASE_URL 改成你的 LAN IP + :8001
```

Expo 會優先讀 `.env.local`，所以 `.env` 仍可指向正式 API。

## 日常指令

### 啟動 / 維持正式環境（開機後跑一次）

```bash
docker compose -f docker-compose.prod.yml --profile tunnel up -d --build
curl https://vibetrip.codingraccoon.com/healthz
```

### 開始寫後端（dev API，prod 繼續跑）

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.dev-api.yml --profile dev up api-dev -d --build
```

- Swagger：<http://localhost:8001/docs>
- 手機 Expo 指到：`http://<你的 LAN IP>:8001`

### 收工關 dev API

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.dev-api.yml stop api-dev
```

前端改回 `.env` 的正式 URL（或刪除 `.env.local` 後重啟 Expo）。

### 不用 Docker、直接 uvicorn（可選）

prod stack 需已啟動（db/redis 經 127.0.0.1 連線）：

```bash
# 在 vibetrip-backend，已安裝 requirements.txt
uvicorn app.main:app --reload --port 8001 --proxy-headers
```

需在本機 shell 載入 `.env` + `.env.development` 的變數（或只用 `.env.development` 並手動補 API keys）。

## 什麼時候用 `docker compose up`（舊的 dev compose）？

只有當你**暫時不需要 prod**、想整包重來時：

```bash
docker compose -f docker-compose.prod.yml --profile tunnel stop
docker compose up --build
```

這會佔用 `:8000`，與 prod API 衝突，兩者不要同時跑。

## 注意

| 項目 | 說明 |
|------|------|
| 資料庫 | dev / prod 共用；`alembic upgrade` 與 seed 會作用在同一 DB |
| 上傳圖片 | 共用 `uploads_data` volume |
| JWT | dev 與 prod secret 不同 → 在 dev API 登入拿到的 token 不能拿去叫 prod API |
| Schema 變更 | 先在 dev 測完再 deploy prod image（`docker compose -f docker-compose.prod.yml up -d --build api`） |
