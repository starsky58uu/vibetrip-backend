"""
PostgreSQL 連線管理 — 負責存放「靜態資料」。

什麼算靜態？
- 使用者帳號、個人 / 社群足跡
- 公車站牌、捷運站、YouBike 站的座標 (搭配 PostGIS 用一次 SQL 就能算距離)
- 盲盒行程模板

用 async SQLAlchemy 2.0，所有 ORM 操作都是 await。
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


# ---------- 建立引擎 ----------
# pool_pre_ping=True：每次拿連線前先 ping 一下，避免連到已斷掉的 socket
# echo=False：正式環境不要把 SQL 印到 log (開發時可設為 True 方便除錯)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


# ---------- Session 工廠 ----------
# expire_on_commit=False：commit 之後不要讓 ORM 物件失效
# (不然在 FastAPI 回傳 response 時常常會觸發非同步 re-fetch)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 的依賴注入 (Dependency Injection)：
    在 endpoint 裡只要寫 db: AsyncSession = Depends(get_db)，
    這個函式會幫你開一個 session、請求結束後自動關閉。

    如果 endpoint 拋例外，會自動 rollback。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
