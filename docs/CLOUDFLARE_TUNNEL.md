# Cloudflare Tunnel 設定指南

把本機（或伺服器）上跑的 VibeTrip API 透過 Cloudflare Tunnel 公開到網際網路，**不必**在路由器開 port 或設定固定 IP。

架構：

```
Internet → Cloudflare Edge → cloudflared → api:8000 (FastAPI)
                              ↑
                    與 api 同一個 Docker network
```

`db` 與 `redis` 仍只對內網開放，不會經由 tunnel 暴露。

---

## 前置條件

1. 網域已加入 [Cloudflare](https://dash.cloudflare.com)（免費方案即可）。
2. 本機已能正常啟動後端：

   ```bash
   docker compose up -d --build
   curl http://localhost:8000/healthz
   ```

---

## 方式 A：Tunnel Token（建議，最簡單）

適合：想用 Cloudflare Zero Trust 網頁介面管理路由。

### 1. 在 Cloudflare 建立 Tunnel

1. 登入 [Cloudflare Zero Trust](https://one.dash.cloudflare.com/)（或 Dashboard → **Zero Trust**）。
2. **Networks** → **Tunnels** → **Create a tunnel**。
3. 名稱例如 `vibetrip-api`，選 **Cloudflared** → **Next**。
4. 在 **Install connector** 頁選 **Docker**，複製 **Token**（很長的一串）。

### 2. 寫入 `.env`

```env
CLOUDFLARE_TUNNEL_TOKEN=貼上剛才複製的 token
```

### 3. 在 Dashboard 設定 Public Hostname

仍在同一個 tunnel 設定頁：

| 欄位 | 值 |
|------|-----|
| **Subdomain** | 例如 `api`（完整網址會是 `api.yourdomain.com`） |
| **Domain** | 你的網域 |
| **Type** | HTTP |
| **URL** | `http://api:8000` |

> **重要**：URL 必須是 `http://api:8000`，不是 `localhost:8000`。  
> `cloudflared` 容器與 `api` 容器在同一個 Docker network，主機名是 compose 裡的 service 名稱 `api`。

可再加一條把 `api.yourdomain.com/docs` 也指到同一個 service（同一條 hostname 已涵蓋所有路徑）。

### 4. 啟動 tunnel

```bash
docker compose --profile tunnel up -d
```

確認 connector 在 Zero Trust → Tunnels 顯示 **Healthy**。

### 5. 驗證

```bash
curl https://api.yourdomain.com/healthz
```

瀏覽器開 `https://api.yourdomain.com/docs`。

### 6. 更新公開 URL（上傳圖片等）

若 API 會回傳圖片網址，在 `.env` 設定：

```env
PUBLIC_CDN_BASE=https://api.yourdomain.com/static/uploads
```

然後重啟 API（不必 rebuild）：

```bash
docker compose restart api
```

---

## 方式 B：本機 config + credentials（進階）

適合：想把 ingress 寫在 repo、用 CLI 管理 DNS。

### 1. 安裝 cloudflared（本機一次）

Windows（winget）：

```powershell
winget install Cloudflare.cloudflared
```

或從 [Cloudflare 下載](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) 安裝。

### 2. 登入並建立 tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create vibetrip-api
```

記下輸出的 **Tunnel ID**。

### 3. 設定 DNS（擇一）

```bash
cloudflared tunnel route dns vibetrip-api api.yourdomain.com
```

或在 Cloudflare DNS 手動加 CNAME：`api` → `<TUNNEL_ID>.cfargotunnel.com`（Proxied）。

### 4. 放 credentials 與 config

```bash
# credentials 通常在 %USERPROFILE%\.cloudflared\<TUNNEL_ID>.json
copy "%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json" cloudflared\credentials.json

copy cloudflared\config.yml.example cloudflared\config.yml
```

編輯 `cloudflared/config.yml`：填入 tunnel UUID、`hostname`。

### 5. 啟動（config 模式）

在 `.env` **不要**設定 `CLOUDFLARE_TUNNEL_TOKEN`（或留空）。

`docker-compose.yml` 裡 `cloudflared` 已掛載 `./cloudflared`；預設 `command` 使用 `config.yml`。

```bash
docker compose --profile tunnel up -d
```

---

## 方式 C：快速測試（無自訂網域）

不建 tunnel、不綁網域，只要暫時給別人測 API：

```bash
docker compose up -d
cloudflared tunnel --url http://localhost:8000
```

終端機會印出 `https://xxxx.trycloudflare.com`，重開就會換網址。  
**不要**用於正式環境或存放真實密鑰。

---

## 常見問題

### Tunnel Healthy 但 502 / connection refused

- Public Hostname 的 URL 是否為 `http://api:8000`（不是 `127.0.0.1`）。
- `api` 是否在跑：`docker compose ps`。
- 先在本機確認：`curl http://localhost:8000/healthz`。

### 只啟動 API、不要 tunnel

```bash
docker compose up -d
```

不加 `--profile tunnel` 就不會啟動 `cloudflared`。

### 前端 / App 要連哪個 base URL

把 API base 設成 tunnel 網址，例如：

`https://api.yourdomain.com/api/v1`

CORS 目前允許 `*`；上線建議在 `app/main.py` 改成你的 App 網域。

### 正式環境建議

| 項目 | 建議 |
|------|------|
| `DEBUG` | `false` |
| `JWT_SECRET_KEY` | 強隨機字串 |
| uvicorn | 拿掉 `--reload`，用多 worker 或反向 proxy |
| Tunnel | 用方式 A 或 B，不要用 trycloudflare |

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `docker-compose.yml` | `cloudflared` service（profile: `tunnel`） |
| `cloudflared/config.yml.example` | 方式 B 的 ingress 範例 |
| `.env.example` | `CLOUDFLARE_TUNNEL_TOKEN`、`PUBLIC_CDN_BASE` |
