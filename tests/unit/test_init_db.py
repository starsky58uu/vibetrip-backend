"""init_db seed 邏輯測試。"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.init_db import init_db


@pytest.mark.asyncio
async def test_init_db_skips_seed_when_nonempty() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=5)))
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_local():
        yield session

    with (
        patch("app.db.init_db.run_migrations", AsyncMock()),
        patch("app.db.init_db.AsyncSessionLocal", _session_local),
    ):
        await init_db()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_init_db_seeds_when_empty() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one=MagicMock(return_value=0)))
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _session_local():
        yield session

    with (
        patch("app.db.init_db.run_migrations", AsyncMock()),
        patch("app.db.init_db.AsyncSessionLocal", _session_local),
    ):
        await init_db()
    assert session.add.call_count > 0
    session.commit.assert_awaited_once()
