"""盲盒行程端點。"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
    """取單一行程 — 供分享 / 歷史查詢。"""
    return await trip_service.get_trip(db, trip_id)
