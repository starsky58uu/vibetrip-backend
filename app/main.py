"""
VibeTrip API 進入點。

啟動流程：
1. 建立 FastAPI app，掛載 CORS + v1 路由
2. startup 時：驗證 DB/Redis、建表 + seed
3. shutdown 時：關 Redis
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api_router import api_router
from app.core.config import settings
from app.core.health import check_database, check_redis, readiness
from app.core.redis_client import close_redis, get_redis
from app.db.init_db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("VibeTrip API starting…")

    if not await check_database():
        raise RuntimeError("無法連線 PostgreSQL，請確認 DB 服務已啟動")

    if not await check_redis():
        raise RuntimeError("無法連線 Redis，請確認 Redis 服務已啟動")

    await init_db()
    await get_redis()
    logger.info("VibeTrip API started ✅")

    yield

    await close_redis()
    logger.info("VibeTrip API stopped")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="專為 P 型旅人打造的即時盲盒行程 App 後端 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

_upload_dir = Path(settings.UPLOAD_DIR)
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=str(_upload_dir)), name="static_uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["系統"])
def root() -> dict:
    body: dict = {
        "message": "Welcome to VibeTrip API! 🚀",
        "status": "running",
    }
    if settings.DEBUG:
        body["docs"] = "/docs"
    return body


@app.get("/healthz", tags=["系統"])
async def healthz():
    """給 Docker / K8s 探測；DB 或 Redis 異常時回 503。"""
    checks = await readiness()
    all_ok = all(checks.values())
    body = {"status": "ok" if all_ok else "degraded", **checks}
    if not all_ok:
        return JSONResponse(body, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return body
