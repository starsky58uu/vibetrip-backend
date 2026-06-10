"""
Redis 連線管理 — 負責「動態資料」的快取。

什麼算動態？
- 公車/捷運即時到站時間 (TDX 每 15 秒才更新一次，所以快取 15 秒很合理)
- YouBike 可借/可還車輛數
- 天氣 (10 分鐘內重複查詢直接回快取)

所有 key 都經過 build_key() 加上 namespace 前綴，避免跟其他專案打架。
"""

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings

# ---------- 全域 client ----------
# 整個 App 共用同一個 connection pool，由 redis-py 內部管理
# decode_responses=True：讓 get/set 直接用 str，不用每次自己 decode
_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """
    FastAPI 依賴：在 endpoint 裡 Depends(get_redis) 就能拿到共用 client。
    第一次呼叫時才建立連線 (lazy init)。
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """App shutdown 時呼叫，關閉連線池。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


# ---------- 輔助函式 ----------
# 統一管理 key 命名，避免打字錯誤
NAMESPACE = "vibetrip"


def build_key(*parts: Any) -> str:
    """
    把多個片段組成 redis key，格式：vibetrip:part1:part2:part3

    例：build_key("bus", "207", "市政府站") -> "vibetrip:bus:207:市政府站"
    """
    return ":".join([NAMESPACE, *[str(p) for p in parts]])


async def cache_get_json(client: redis.Redis, key: str) -> Any | None:
    """讀 key，如果有就反序列化成 Python 物件 (dict/list/...)。"""
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set_json(
    client: redis.Redis,
    key: str,
    value: Any,
    ttl_seconds: int,
) -> None:
    """序列化成 JSON 存進 redis，並設過期時間 (TTL)。"""
    await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)


async def scan_delete_pattern(client: redis.Redis, pattern: str) -> int:
    """
    用 SCAN 刪除符合 pattern 的 key（避免 KEYS 阻塞 Redis）。
    回傳刪除筆數。
    """
    deleted = 0
    async for key in client.scan_iter(match=pattern, count=100):
        await client.delete(key)
        deleted += 1
    return deleted
