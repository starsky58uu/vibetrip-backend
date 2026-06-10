"""Redis client 輔助函式測試。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core import redis_client as rc


@pytest.fixture(autouse=True)
def _reset_redis_client() -> None:
    rc._redis_client = None
    yield
    rc._redis_client = None


def test_build_key() -> None:
    assert rc.build_key("bus", 207, "站") == "vibetrip:bus:207:站"


@pytest.mark.asyncio
async def test_get_redis_lazy_init() -> None:
    mock_client = AsyncMock()
    with patch("app.core.redis_client.redis.from_url", return_value=mock_client) as from_url:
        c1 = await rc.get_redis()
        c2 = await rc.get_redis()
    assert c1 is c2 is mock_client
    from_url.assert_called_once()


@pytest.mark.asyncio
async def test_close_redis() -> None:
    mock_client = AsyncMock()
    rc._redis_client = mock_client
    await rc.close_redis()
    mock_client.close.assert_awaited_once()
    assert rc._redis_client is None


@pytest.mark.asyncio
async def test_cache_get_json_miss_and_hit() -> None:
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    assert await rc.cache_get_json(client, "k") is None

    payload = {"a": 1}
    client.get = AsyncMock(return_value=json.dumps(payload))
    assert await rc.cache_get_json(client, "k") == payload


@pytest.mark.asyncio
async def test_cache_set_json() -> None:
    client = AsyncMock()
    await rc.cache_set_json(client, "k", {"x": "中文"}, ttl_seconds=60)
    client.set.assert_awaited_once()
    args = client.set.await_args
    assert json.loads(args[0][1]) == {"x": "中文"}
    assert args[1]["ex"] == 60


@pytest.mark.asyncio
async def test_scan_delete_pattern() -> None:
    client = AsyncMock()

    async def _iter(*_a, **_k):
        for key in ("a", "b"):
            yield key

    client.scan_iter = _iter
    client.delete = AsyncMock()
    deleted = await rc.scan_delete_pattern(client, "vibetrip:test:*")
    assert deleted == 2
    assert client.delete.await_count == 2
