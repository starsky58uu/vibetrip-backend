# 資料庫 Migrations（Alembic）

Schema 變更**不要**再改 `create_all()` 或手寫 `ALTER` in `init_db`。  
流程：**改 ORM model → 產生 migration → commit → deploy 時 `upgrade head`**。

---

## 日常指令

```bash
# 套用所有未執行的 migration（啟動時 init_db 也會自動跑）
python -m alembic upgrade head

# 目前版本
python -m alembic current

# 歷史
python -m alembic history --verbose
```

Docker 內：

```bash
docker compose exec api python -m alembic upgrade head
```

---

## 新增 migration

1. 修改 `app/db/models/*.py`
2. 產生 revision（自動比對 model 與 DB）：

```bash
alembic revision --autogenerate -m "describe_your_change"
```

3. **人工檢查** `alembic/versions/*.py`（autogenerate 常漏 PostGIS 索引或漏改）
4. 本地 `alembic upgrade head` 驗證
5. 若有測試依賴 schema，跑 `pytest -v`

手寫 migration（小改動）：

```bash
alembic revision -m "add_foo_column"
```

---

## 目錄

```
alembic/
├── env.py              # async engine，讀 app.core.config
├── script.py.mako
└── versions/
    ├── 001_initial_schema.py
    └── 002_community_personal_spot_link.py
```

---

## 從舊版 `create_all` 升級

若 DB **已有表**、但沒有 `alembic_version` 表：

```bash
# 標記已在 001 狀態（不重建表）
alembic stamp 001_initial

# 再套用後續 migration
alembic upgrade head
```

全新環境：直接 `alembic upgrade head` 或 `docker compose up`（startup 會跑）。

---

## 注意事項

- PostGIS：`001_initial` 會 `CREATE EXTENSION IF NOT EXISTS postgis`
- Geography 欄位：autogenerate 可能不完整，複雜空間變更請手寫 SQL
- **不要**在 production 用 `Base.metadata.drop_all()`；downgrade 僅供開發還原
- Seed 資料仍在 `app/db/init_db.py`，與 migration 分離

---

## 相關

- [CONVENTIONS.md](CONVENTIONS.md) — 分層與 DB 慣例
- [TESTING.md](TESTING.md) — schema 變更請附測試
