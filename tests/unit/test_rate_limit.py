"""Rate limiter 單元測試。"""

import pytest

from app.core.rate_limit import check_rate_limit, client_ip
from app.core.redis_client import build_key


class _FakeRedis:
    """最小 Redis 假物件，模擬 INCR + EXPIRE + TTL。"""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = seconds

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)


@pytest.mark.asyncio
async def test_allows_under_limit() -> None:
    redis = _FakeRedis()
    for _ in range(3):
        allowed, _ = await check_rate_limit(
            redis, scope="test", identity="1.2.3.4", limit=3, window_seconds=60
        )
        assert allowed is True


@pytest.mark.asyncio
async def test_blocks_over_limit() -> None:
    redis = _FakeRedis()
    for _ in range(2):
        await check_rate_limit(redis, scope="test", identity="1.2.3.4", limit=2, window_seconds=60)
    allowed, retry_after = await check_rate_limit(
        redis, scope="test", identity="1.2.3.4", limit=2, window_seconds=60
    )
    assert allowed is False
    assert retry_after >= 1


@pytest.mark.asyncio
async def test_zero_limit_means_unlimited() -> None:
    redis = _FakeRedis()
    allowed, _ = await check_rate_limit(
        redis, scope="test", identity="x", limit=0, window_seconds=60
    )
    assert allowed is True


def test_client_ip_direct() -> None:
    class _Client:
        host = "192.168.1.1"

    class _Req:
        headers = {}
        client = _Client()

    assert client_ip(_Req()) == "192.168.1.1"  # type: ignore[arg-type]


def test_client_ip_unknown() -> None:
    class _Req:
        headers = {}
        client = None

    assert client_ip(_Req()) == "unknown"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ttl_negative_reexpires() -> None:
    redis = _FakeRedis()
    await check_rate_limit(redis, scope="t", identity="x", limit=5, window_seconds=60)
    key = build_key("ratelimit", "t", "x")
    redis._ttl[key] = -1
    allowed, _ = await check_rate_limit(redis, scope="t", identity="x", limit=5, window_seconds=60)
    assert allowed is True
    assert redis._ttl.get(key) == 60


@pytest.mark.asyncio
async def test_enforce_rate_limit_disabled(monkeypatch) -> None:
    from app.core import rate_limit as rl

    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", False)
    await rl.enforce_rate_limit(_FakeRedis(), scope="s", identity="i", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_enforce_rate_limit_raises_429(monkeypatch) -> None:
    from fastapi import HTTPException

    from app.core import rate_limit as rl

    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", True)
    redis = _FakeRedis()
    for _ in range(2):
        await rl.check_rate_limit(redis, scope="s", identity="i", limit=1, window_seconds=60)
    with pytest.raises(HTTPException) as exc:
        await rl.enforce_rate_limit(redis, scope="s", identity="i", limit=1, window_seconds=60)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


@pytest.mark.asyncio
async def test_rate_limit_trips_and_uploads(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.core import rate_limit as rl

    monkeypatch.setattr(rl.settings, "RATE_LIMIT_ENABLED", False)
    req = MagicMock()
    req.headers = {}
    req.client = MagicMock(host="1.2.3.4")
    with patch("app.core.rate_limit.get_redis", AsyncMock(return_value=_FakeRedis())):
        await rl.rate_limit_trips_recommend(req)
        await rl.rate_limit_upload_image("user-1")


def test_client_ip_from_x_forwarded_for() -> None:
    class _Client:
        host = "10.0.0.1"

    class _Req:
        headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        client = _Client()

    assert client_ip(_Req()) == "203.0.113.5"  # type: ignore[arg-type]
