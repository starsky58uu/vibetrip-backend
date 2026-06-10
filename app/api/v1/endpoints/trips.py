"""盲盒行程端點。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.redis_client import get_redis, scan_delete_pattern
from app.db.models.user import User
from app.schemas.trip import RecommendRequest, TripPlanResponse
from app.services import trip_service

router = APIRouter()


@router.post("/recommend", response_model=TripPlanResponse)
async def recommend_trip(
    req: RecommendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripPlanResponse:
    """
    依心情 / 位置 / 天氣產生一份盲盒行程。
    每次呼叫都會隨機挑一個 — 前端「搖一搖」功能就是再打一次這支。
    """
    return await trip_service.recommend(db, req)


@router.get("/{trip_id}", response_model=TripPlanResponse)
async def get_trip(
    trip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripPlanResponse:
    """取單一行程 — 供分享 / 歷史查詢（僅 DB 模板；AI 行程 ID 不持久化）。"""
    return await trip_service.get_trip(db, trip_id)


@router.delete("/cache", summary="清除行程 AI 快取（僅 DEBUG）")
async def clear_trip_cache(
    _user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    清除所有 vibetrip:trip:ai:* 快取。
    僅在 DEBUG=true 時可用；需登入。
    """
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此端點僅供開發環境使用",
        )

    redis = await get_redis()
    deleted = await scan_delete_pattern(redis, "vibetrip:trip:ai:*")
    return {"deleted": deleted, "message": f"已清除 {deleted} 筆行程快取"}
