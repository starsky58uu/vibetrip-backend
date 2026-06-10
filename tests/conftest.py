"""
pytest 共用設定。

在 import app 之前設定測試用環境變數，避免觸發 production 密鑰檢查。

測試政策與撰寫指南：docs/TESTING.md
新功能請在 tests/unit/ 或 tests/api/ 補案例，合併前跑 pytest -v。
"""

import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# 必須在 import app 模組之前
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET_KEY", "pytest-secret-key-not-for-production")

from app.core.config import get_settings

get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """
    打 API 用的 async client。

    Mock 掉 lifespan 裡的 DB/Redis/init，讓 CI 不必起 Docker 也能跑 smoke test。
    """
    patches = [
        patch("app.main.check_database", AsyncMock(return_value=True)),
        patch("app.main.check_redis", AsyncMock(return_value=True)),
        patch("app.main.init_db", AsyncMock()),
        patch("app.main.get_redis", AsyncMock()),
        patch("app.main.close_redis", AsyncMock()),
    ]
    for p in patches:
        p.start()
    try:
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        for p in reversed(patches):
            p.stop()
