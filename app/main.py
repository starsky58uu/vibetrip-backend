"""
VibeTrip API 進入點。

啟動流程：
1. 建立 FastAPI app，掛載 CORS + v1 路由
2. startup 時：連 Redis、(開發環境) 自動建表 + seed
3. shutdown 時：關 Redis
"""
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.api_router import api_router
from app.core.config import settings
from app.core.redis_client import close_redis, get_redis
from app.db.init_db import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="專為 P 型旅人打造的即時盲盒行程 App 後端 API",
    version="1.0.0",
)

# ── 靜態圖片服務 ─────────────────────────────────────────────────────────────
# 讓 /static/uploads/<filename> 可直接存取已上傳的足跡圖片
_upload_dir = Path(settings.UPLOAD_DIR)
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=str(_upload_dir)), name="static_uploads")

# ---------- CORS ----------
# 開發階段允許所有來源，上線務必改成 App 的實際網域 (或用環境變數控制)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 掛載 v1 路由 ----------
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# ---------- 生命週期事件 ----------
@app.on_event("startup")
async def on_startup() -> None:
    """啟動時建表 + 暖身 Redis 連線。"""
    logger.info("VibeTrip API starting…")

    # 建表 + seed 盲盒行程 (正式環境建議改用 Alembic migration)
    try:
        await init_db()
    except Exception as e:
        logger.exception("init_db 失敗: %s", e)

    # 預熱 Redis 連線
    await get_redis()
    logger.info("VibeTrip API started ✅")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_redis()
    logger.info("VibeTrip API stopped")


# ---------- Health check ----------
@app.get("/", tags=["系統"])
def root() -> dict:
    return {
        "message": "Welcome to VibeTrip API! 🚀",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/healthz", tags=["系統"])
def healthz() -> dict:
    """給 Docker / K8s 探測存活。"""
    return {"status": "ok"}
