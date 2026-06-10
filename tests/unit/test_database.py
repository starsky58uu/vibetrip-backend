"""get_db 依賴測試。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.database import get_db


@pytest.mark.asyncio
async def test_get_db_yields_and_closes() -> None:
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.core.database.AsyncSessionLocal", return_value=cm):
        gen = get_db()
        db = await anext(gen)
        assert db is session
        await gen.aclose()
    session.close.assert_awaited()


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_exception() -> None:
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    with patch("app.core.database.AsyncSessionLocal", return_value=cm):
        gen = get_db()
        await anext(gen)
        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))
    session.rollback.assert_awaited()
