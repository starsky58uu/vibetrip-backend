"""main.py lifespan 測試。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from app.main import lifespan


@pytest.mark.asyncio
async def test_lifespan_success() -> None:
    app = FastAPI()
    with (
        patch("app.main.check_database", AsyncMock(return_value=True)),
        patch("app.main.check_redis", AsyncMock(return_value=True)),
        patch("app.main.init_db", AsyncMock()),
        patch("app.main.get_redis", AsyncMock()),
        patch("app.main.close_redis", AsyncMock()) as close_redis,
    ):
        async with lifespan(app):
            pass
    close_redis.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_db_failure() -> None:
    app = FastAPI()
    with patch("app.main.check_database", AsyncMock(return_value=False)):
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            async with lifespan(app):
                pass


@pytest.mark.asyncio
async def test_lifespan_redis_failure() -> None:
    app = FastAPI()
    with (
        patch("app.main.check_database", AsyncMock(return_value=True)),
        patch("app.main.check_redis", AsyncMock(return_value=False)),
    ):
        with pytest.raises(RuntimeError, match="Redis"):
            async with lifespan(app):
                pass
