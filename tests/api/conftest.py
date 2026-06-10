"""API 測試共用 fixture。"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_user


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.avatar_url = None
    user.created_at = None
    user.hashed_password = "hashed"
    return user


@pytest.fixture
async def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def authed_client(mock_user, mock_db) -> AsyncIterator[AsyncClient]:
    """帶登入使用者與 mock DB 的 client。"""
    from unittest.mock import patch

    patches = [
        patch("app.main.check_database", AsyncMock(return_value=True)),
        patch("app.main.check_redis", AsyncMock(return_value=True)),
        patch("app.main.init_db", AsyncMock()),
        patch("app.main.get_redis", AsyncMock()),
        patch("app.main.close_redis", AsyncMock()),
    ]
    for p in patches:
        p.start()

    from app.main import app

    async def _user() -> MagicMock:
        return mock_user

    async def _db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_optional_user] = _user
    app.dependency_overrides[get_db] = _db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    for p in reversed(patches):
        p.stop()
