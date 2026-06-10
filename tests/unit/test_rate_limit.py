"""Rate limiter 單元測試。"""

import pytest

from app.core.rate_limit import check_rate_limit, client_ip


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


def test_client_ip_from_x_forwarded_for() -> None:
    class _Client:
        host = "10.0.0.1"

    class _Req:
        headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        client = _Client()

    assert client_ip(_Req()) == "203.0.113.5"  # type: ignore[arg-type]
