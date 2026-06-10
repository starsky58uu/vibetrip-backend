"""
整合測試 fixture — 需要真實 PostgreSQL + Redis。

本機沒有 Docker 時會自動 skip；CI 透過 service containers 提供。
"""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET_KEY", "pytest-ci-secret-key")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "tdx_user")
os.environ.setdefault("DB_PASSWORD", "test_password")
os.environ.setdefault("DB_NAME", "tdx_database")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from app.core.config import get_settings

get_settings.cache_clear()


@pytest_asyncio.fixture
async def _integration_ready() -> AsyncIterator[None]:
    """確認依賴可用並跑 migrate + seed。"""
    from app.core.database import engine
    from app.core.health import check_database, check_redis
    from app.core.redis_client import close_redis
    from app.db.init_db import init_db

    if not await check_database():
        pytest.skip("PostgreSQL 不可用 — 請啟動 docker compose db")
    if not await check_redis():
        pytest.skip("Redis 不可用 — 請啟動 docker compose redis")

    await init_db()
    yield
    await close_redis()
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_integration_ready):
    """每個測試獨立 session，結束後 rollback。"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def integration_client(_integration_ready) -> AsyncIterator[AsyncClient]:
    """打真實 API（lifespan 會連 DB/Redis，init_db 可重複執行）。"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
