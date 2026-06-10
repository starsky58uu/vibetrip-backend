"""Alembic migrate 包裝測試。"""

from unittest.mock import MagicMock, patch

import pytest

from app.db.migrate import run_migrations, upgrade_head


def test_upgrade_head_calls_alembic() -> None:
    with patch("app.db.migrate.command.upgrade") as upgrade:
        upgrade_head()
    upgrade.assert_called_once()


@pytest.mark.asyncio
async def test_run_migrations_async() -> None:
    with patch("app.db.migrate.upgrade_head", MagicMock()) as upgrade:
        await run_migrations()
    upgrade.assert_called_once()
