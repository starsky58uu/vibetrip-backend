# VibeTrip Backend — 改進路線圖

> 從 code review 整理出的分階段計畫；完成項打 ✅，進行中打 🚧。

---

## P0 — 安全與維運基線 ✅

- [x] CORS 改為環境變數 `CORS_ORIGINS`
- [x] `/healthz` 檢查 DB + Redis
- [x] 啟動時 DB/Redis 連不上則 fail fast
- [x] `DEBUG=false` 時拒絕預設 `JWT_SECRET_KEY`
- [x] 鎖定 `DELETE /trips/cache`（需登入 + DEBUG）
- [x] 移除 `/blindbox/test`
- [x] 修正 `.env.example` 的 `GOOGLE_MAPS_API_KEY`

## P1 — 可靠性 ✅

- [x] 公車 ETA status 順序修正
- [x] Google API `status` 欄位檢查
- [x] 按讚 / 收藏原子計數
- [x] 個人足跡 ↔ 社群貼文同步（`personal_spot_id`）
- [x] `print()` → `logger`

## P2 — 可讀性與 API 契約 ✅

- [x] `docs/CONVENTIONS.md`
- [x] Response schemas（stats / taste / upload）
- [x] Ruff lint + format
- [x] pre-commit hooks
- [x] GitHub Actions lint

## P3 — 測試與擴展 🚧

- [x] pytest 單元測試（security、trip、transit、AI 驗證）
- [x] API smoke tests（root、healthz，mock 依賴）
- [x] CI 跑 pytest
- [x] [docs/TESTING.md](TESTING.md) — 測試政策（新功能必附測試、給 LLM 的指引）
- [ ] CI 覆蓋率門檻（`pytest-cov` + `--cov-fail-under`）
- [ ] 整合測試（需 Docker DB/Redis）
- [ ] Alembic migrations
- [ ] 拆分 `ai_service.py`
- [ ] Rate limiting（`/trips/recommend`、`/uploads/image`）
- [ ] 社群 feed 分頁
- [ ] Refresh token rotation
- [ ] AI 行程持久化或明確文件化 `GET /trips/{id}` 限制

---

最後更新：依目前 repo 狀態維護；完成 P3 項目時請同步勾選。
