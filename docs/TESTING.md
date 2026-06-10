# 測試指南

> **給人類開發者與 AI 助手**：本專案預期**每次新增或修改功能都要附帶測試**。CI 會跑 pytest；沒測試的 PR 不應合併。

---

## 1. 政策（必讀）

| 規則 | 說明 |
|------|------|
| **新功能要有測試** | 新 endpoint、service 邏輯、bug fix 都應在 `tests/` 加對應案例 |
| **改舊 code 要跑全套** | `pytest -v` 全綠再 commit / 開 PR |
| **先寫可測的 code** | 複雜邏輯放在 service 純函式，不要全塞在 endpoint |
| **mock 外部依賴** | Groq、Google、TDX、Redis、DB 在單元測試中 mock，不要打真 API |
| **整合測試可選但加分** | 需 Docker 的 full-stack 測試見下方「整合測試」— 尚未強制 |

### 給 AI / LLM 助手

當你被要求實作或修改後端功能時：

1. **先讀** [CONVENTIONS.md](CONVENTIONS.md) 的分層與命名。
2. **實作完成後**在 `tests/unit/` 或 `tests/api/` 新增測試。
3. **執行** `pytest -v`（或 Docker 指令，見下方）確認通過。
4. **在 PR 描述**簡述測了什麼、沒測什麼（若有）。
5. 不要只改 `app/` 而不動 `tests/` — 這會被視為未完成。

---

## 2. 什麼時候寫哪種測試

| 你改了什麼 | 放哪裡 | 範例 |
|------------|--------|------|
| 純函式、解析、驗證邏輯 | `tests/unit/` | `_resolve_vibe`、`_parse_bus_eta`、`_validate_activities` |
| JWT / 密碼 | `tests/unit/test_security.py` | 新 claim、新 token 類型 |
| 新 REST 端點 | `tests/api/test_<模組>.py` | mock `get_db` / `get_current_user` 後打 HTTP |
| Bug 修復 | 先寫**會失敗**的 regression test，再修 code | 重現 issue 的最小案例 |
| 只有文案 / comment | 可不寫測試 | — |

### 新 endpoint 最低要求

- [ ] 成功路徑（200/201）至少一個
- [ ] 主要錯誤路徑（401、404、422）各至少一個（若適用）
- [ ] `response_model` 欄位有 assert（不要只 assert status code）

### 新 service 函式最低要求

- [ ] 正常輸入 → 預期輸出
- [ ] 邊界條件（空列表、None、非法參數）
- [ ] 若修過 production bug → regression case 寫進測試名稱

---

## 3. 怎麼跑

### 本機（Python 3.11+）

```bash
cd vibetrip-backend
pip install -r requirements-dev.txt
pytest -v
```

### 本機沒有 3.11（Windows 常見）

```bash
docker compose run --rm -e DEBUG=true -e JWT_SECRET_KEY=pytest-ci-secret-key api \
  sh -c "pip install pytest pytest-asyncio -q && python -m pytest -v"
```

### 常用指令

```bash
pytest tests/unit -v              # 只跑單元（快、不需 DB）
pytest tests/api -v               # API smoke
pytest tests/unit/test_security.py -v   # 單一檔案
pytest -k "rainy" -v              # 名稱關鍵字過濾
```

### 覆蓋率（建議本地跑，了解缺口）

```bash
pip install pytest-cov
pytest --cov=app --cov-report=term-missing
```

目標：**新改的模組盡量維持或提高覆蓋率**；全 repo 百分比門檻尚未在 CI 強制（見 ROADMAP）。

---

## 4. 目錄結構

```
tests/
├── conftest.py          # 共用 fixture（測試用 env、mock lifespan 的 client）
├── unit/                # 不依賴真實 DB/Redis 的邏輯測試
│   test_security.py
│   test_trip_service.py
│   test_transit_service.py
│   test_ai_service.py
└── api/                 # 透過 HTTP 打 FastAPI（依賴 mock）
    test_system.py
```

命名：`test_<行為>_<條件>()`，例如 `test_rainy_walk_becomes_rain`。

---

## 5. Fixture 與 mock 慣例

- **環境變數**：`tests/conftest.py` 已設 `DEBUG=true` 與測試用 `JWT_SECRET_KEY`
- **API client**：用 `client` fixture（已 mock DB/Redis startup）
- **打 DB 的測試**：目前列在 ROADMAP 待辦；實作時用 `pytest.mark.integration` + Docker Compose

```python
# 範例：mock 外部 API
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_recommend_falls_back_to_db(monkeypatch):
    monkeypatch.setattr(
        "app.services.trip_service.generate_trip",
        AsyncMock(side_effect=RuntimeError("AI down")),
    )
    ...
```

---

## 6. CI

GitHub Actions [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) 在 push/PR 時自動：

1. Ruff check + format
2. `pytest -v`

**本地與 CI 行為應一致**；合併前確認 Actions 全綠。

---

## 7. PR / commit 檢查清單

提交前自問：

- [ ] `pytest -v` 全過？
- [ ] `pre-commit run --all-files` 或至少 Ruff 全過？
- [ ] 新邏輯有對應測試？
- [ ] 測試名稱讀得出在測什麼？
- [ ] 需要更新 `docs/API.md` 嗎？

---

## 8. 相關文件

- [CONVENTIONS.md](CONVENTIONS.md) — 程式風格與分層
- [ROADMAP.md](ROADMAP.md) — 測試路線圖（整合測試、覆蓋率門檻等待辦）
- [API.md](API.md) — 端點規格
