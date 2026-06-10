"""
依賴存活檢查。

- `main.py` lifespan：啟動時 DB / Redis 連不上則直接失敗
- `GET /healthz`：執行期探測，異常回 503
"""

from sqlalchemy import text

from app.core.database import engine
from app.core.redis_client import get_redis


async def check_database() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis() -> bool:
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False


async def readiness() -> dict[str, bool]:
    db_ok = await check_database()
    redis_ok = await check_redis()
    return {"database": db_ok, "redis": redis_ok}
