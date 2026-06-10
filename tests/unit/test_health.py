"""健康檢查測試。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.health import check_database, check_redis, readiness


@pytest.mark.asyncio
async def test_check_database_ok() -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.core.health.engine") as engine:
        engine.connect.return_value = cm
        assert await check_database() is True


@pytest.mark.asyncio
async def test_check_database_failure() -> None:
    with patch("app.core.health.engine") as engine:
        engine.connect.side_effect = RuntimeError("db down")
        assert await check_database() is False


@pytest.mark.asyncio
async def test_check_redis_ok() -> None:
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    with patch("app.core.health.get_redis", AsyncMock(return_value=client)):
        assert await check_redis() is True


@pytest.mark.asyncio
async def test_check_redis_failure() -> None:
    with patch("app.core.health.get_redis", AsyncMock(side_effect=RuntimeError("redis down"))):
        assert await check_redis() is False


@pytest.mark.asyncio
async def test_readiness_combines_checks() -> None:
    with (
        patch("app.core.health.check_database", AsyncMock(return_value=True)),
        patch("app.core.health.check_redis", AsyncMock(return_value=False)),
    ):
        result = await readiness()
    assert result == {"database": True, "redis": False}
