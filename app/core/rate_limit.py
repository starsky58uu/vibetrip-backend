"""
Redis 固定視窗 rate limiter。

多 worker / 多容器共用同一組 Redis 計數，比 in-memory 限流可靠。
"""

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import build_key, get_redis


def client_ip(request: Request) -> str:
    """取客戶端 IP（支援 reverse proxy 的 X-Forwarded-For）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def check_rate_limit(
    client: redis.Redis,
    *,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """
    固定視窗計數。回傳 (allowed, retry_after_seconds)。
    retry_after 僅在 allowed=False 時有意義。
    """
    if limit <= 0:
        return True, 0

    key = build_key("ratelimit", scope, identity)
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, window_seconds)

    ttl = await client.ttl(key)
    if ttl < 0:
        await client.expire(key, window_seconds)
        ttl = window_seconds

    if count > limit:
        return False, max(int(ttl), 1)
    return True, 0


async def enforce_rate_limit(
    client: redis.Redis,
    *,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    """超過限額時拋 429，並帶 Retry-After header。"""
    if not settings.RATE_LIMIT_ENABLED:
        return

    allowed, retry_after = await check_rate_limit(
        client,
        scope=scope,
        identity=identity,
        limit=limit,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="請求過於頻繁，請稍後再試",
            headers={"Retry-After": str(retry_after)},
        )


async def rate_limit_trips_recommend(request: Request) -> None:
    """POST /trips/recommend — 依 IP 限流（AI + Google 成本高）。"""
    redis_client = await get_redis()
    await enforce_rate_limit(
        redis_client,
        scope="trips_recommend",
        identity=client_ip(request),
        limit=settings.RATE_LIMIT_TRIPS_PER_MINUTE,
        window_seconds=60,
    )


async def rate_limit_upload_image(user_id: str) -> None:
    """POST /uploads/image — 依使用者 ID 限流。"""
    redis_client = await get_redis()
    await enforce_rate_limit(
        redis_client,
        scope="uploads_image",
        identity=user_id,
        limit=settings.RATE_LIMIT_UPLOADS_PER_HOUR,
        window_seconds=3600,
    )
