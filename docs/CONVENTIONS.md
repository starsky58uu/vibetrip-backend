# 後端程式風格與慣例

> 給未來的自己與協作者：讓每個檔案打開來都長得像同一個人寫的。

---

## 1. 分層職責（最重要）

| 層 | 目錄 | 做什麼 | 不做什麼 |
|----|------|--------|----------|
| **路由** | `api/v1/endpoints/` | 參數驗證、`Depends`、呼叫 service、回傳 schema | 不寫 SQL、不直呼外部 API |
| **業務** | `services/` | 流程編排、快取策略、拋 `HTTPException` | 不碰 `Request` / `Response` |
| **外部** | `services/external/` | 單一第三方 HTTP 包裝 | 不做快取（快取在 service） |
| **資料** | `db/models/` | ORM 定義 | 不寫業務邏輯 |
| **契約** | `schemas/` | Request / Response 的 Pydantic 模型 | 不 import service |
| **基礎** | `core/` | 設定、連線、JWT、共用依賴 | 不寫領域邏輯 |

**資料流**：`endpoint → service → (db | redis | external client)`

---

## 2. 檔案開頭

每個 `.py` 檔最上方用 **一行或短段落** 說明職責（繁中即可）：

```python
"""足跡服務層 — 個人足跡與社群地標的 CRUD、按讚、收藏。"""
```

- Service / core：可多加 2～3 行說明快取或 PostGIS 策略
- Endpoint：一句話 + 必要時列主要路由

---

## 3. import 順序

依 [PEP 8](https://peps.python.org/pep-0008/#imports)：

1. 標準庫（`logging`, `uuid`, …）
2. 第三方（`fastapi`, `sqlalchemy`, `redis`, …）
3. 本專案（`app.core…`, `app.services…`）

各區塊之間空一行。`from __future__ import annotations` 永遠放最前。

```python
from typing import Annotated

from fastapi import APIRouter, Depends
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import spot_service
```

---

## 4. 命名

| 種類 | 風格 | 範例 |
|------|------|------|
| 模組 | `snake_case` | `spot_service.py` |
| 類別 | `PascalCase` | `CommunitySpot` |
| 函式 / 變數 | `snake_case` | `list_community_spots` |
| 常數 | `UPPER_SNAKE` | `CACHE_TTL` |
| 私有 helper | `_leading_underscore` | `_sync_community_from_personal` |
| Redis key | `build_key(...)` | `vibetrip:weather:current:25.03:121.56` |

API 路徑用 **複數名詞 + kebab 少見**：`/spots/personal`, `/trips/recommend`。

---

## 5. 型別與語法

- Python **3.11+** 語法：`str | None` 優於 `Optional[str]`
- 需要時才用 `from typing import Annotated`
- FastAPI 依賴一律：`user: Annotated[User, Depends(get_current_user)]`
- 所有 endpoint 宣告 **`response_model`** 與回傳型別註解

---

## 6. 錯誤與日誌

- 業務錯誤在 **service** 拋 `HTTPException(status_code=..., detail="繁中說明")`
- **禁止** `print()`；用 `logger = logging.getLogger(__name__)`
  - `logger.info` — 正常流程（快取命中、seed 完成）
  - `logger.warning` — 可降級的外部 API 失敗
  - `logger.exception` — 未預期錯誤（含 stack trace）
- `detail` 給使用者看的繁中；技術細節放 log

---

## 7. 資料庫

- 異步 session：`async with` / `await db.execute`
- 需要座標時優先 **PostGIS SQL**，不要在 Python 迴圈算距離
- 計數欄位（likes_count）用 **原子 UPDATE**，不要 read-modify-write
- Schema 變更：長期用 Alembic；過渡期可在 `init_db` 加 `ADD COLUMN IF NOT EXISTS`

---

## 8. Redis 快取

- Key **必須** 經 `build_key("模組", "動作", ...)` — 前綴 `vibetrip:`
- 讀寫 JSON 用 `cache_get_json` / `cache_set_json`
- 刪除 pattern 用 `scan_delete_pattern`，**禁止** `KEYS` in production

---

## 9. 端點 docstring

Swagger 會顯示函式 docstring，格式建議：

```python
@router.get("/community", response_model=list[CommunitySpotResponse])
async def list_community(...) -> list[CommunitySpotResponse]:
    """
    瀏覽社群地標。

    - 匿名可瀏覽；登入後會填入 is_liked / is_saved
    - sort=nearby 時必須帶 lat、lon
    """
```

第一行一句話；細節用 bullet。

---

## 10. 新增功能檢查清單

- [ ] Pydantic schema（request + response）
- [ ] Service 函式（可單獨測試的純邏輯）
- [ ] **測試** — `tests/unit/` 或 `tests/api/`（**必填**，見 [TESTING.md](TESTING.md)）
- [ ] `pytest -v` 全綠
- [ ] Endpoint 薄包裝 + `response_model`
- [ ] 若打外部 API → `external/` client + service 層快取
- [ ] 更新 `docs/API.md` 一筆
- [ ] 敏感端點加 `Depends(get_current_user)`

---

## 11. 語言

- **註解、docstring、HTTP detail**：繁體中文
- **程式識別字**（變數、路徑、log 的 key）：英文
- README / CONVENTIONS / API 文件：繁中為主，技術名詞保留英文

---

## 12. 自動檢查（Ruff）

專案用 [Ruff](https://docs.astral.sh/ruff/) 做 lint + 排版，設定在 `pyproject.toml`。

```bash
# 安裝開發依賴
pip install -r requirements-dev.txt

# 檢查（CI 跑這個）
python -m ruff check app seed_spots.py
python -m ruff format --check app seed_spots.py

# 本地自動修正
python -m ruff check app seed_spots.py --fix
python -m ruff format app seed_spots.py
```

PR 推送時 GitHub Actions（`.github/workflows/ci.yml`）會自動跑。

### pre-commit（建議，commit 前自動跑）

```bash
pip install -r requirements-dev.txt
pre-commit install          # 只需做一次，裝在 .git/hooks/pre-commit
pre-commit run --all-files  # 手動掃描整個 repo
```

之後每次 `git commit`，Ruff 會自動 lint + format；有修正時會改檔並中止 commit，你 `git add` 後再 commit 一次即可。

若暫時要跳過（不建議）：`git commit --no-verify`

---

## 13. 測試（pytest）— 新功能必附測試

**政策**：每次新增或修改後端行為，都要在 `tests/` 補上案例並跑過 `pytest -v`。  
完整說明（含 AI 助手須知、覆蓋率、PR 檢查清單）→ **[docs/TESTING.md](TESTING.md)**

```bash
pip install -r requirements-dev.txt
pytest -v                    # 合併前必跑
pytest tests/unit -v         # 快速：不需 Docker
```

| 目錄 | 內容 |
|------|------|
| `tests/unit/` | 純邏輯：JWT、vibe 解析、公車 ETA、AI 防幻覺 |
| `tests/api/` | HTTP smoke：`/`、`/healthz`（mock DB/Redis） |

CI（`.github/workflows/ci.yml`）會自動跑 pytest；本地全綠再 push。

進度與待辦（整合測試、覆蓋率門檻）→ [docs/ROADMAP.md](ROADMAP.md)。
