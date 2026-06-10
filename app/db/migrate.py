"""
Alembic migration 執行器。

啟動時由 init_db 呼叫，將 schema 升到 head。
"""

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)


def _alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    return Config(str(root / "alembic.ini"))


def upgrade_head() -> None:
    """同步執行 alembic upgrade head（在 thread 中呼叫）。"""
    command.upgrade(_alembic_config(), "head")


async def run_migrations() -> None:
    """非同步包裝 — 供 FastAPI lifespan 使用。"""
    await asyncio.to_thread(upgrade_head)
    logger.info("Alembic migrations applied (head)")
