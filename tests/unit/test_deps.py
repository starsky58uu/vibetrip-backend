"""FastAPI 依賴注入測試。"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.deps import get_current_user, get_optional_user
from app.core.security import create_token


@pytest.mark.asyncio
async def test_get_current_user_no_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_bad_token() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_current_user("not-a-jwt", AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_missing_user() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(token, db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_success() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    user = MagicMock()
    user.id = user_id
    db = AsyncMock()
    db.get = AsyncMock(return_value=user)
    result = await get_current_user(token, db)
    assert result is user


@pytest.mark.asyncio
async def test_get_optional_user_no_token() -> None:
    assert await get_optional_user(None, AsyncMock()) is None


@pytest.mark.asyncio
async def test_get_optional_user_bad_token() -> None:
    assert await get_optional_user("bad", AsyncMock()) is None


@pytest.mark.asyncio
async def test_get_optional_user_success() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    user = MagicMock()
    db = AsyncMock()
    db.get = AsyncMock(return_value=user)
    result = await get_optional_user(token, db)
    assert result is user
