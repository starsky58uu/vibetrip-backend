"""
盲盒行程服務層。

演算法很單純：
1. 根據 vibe_key 找出所有符合的 TripTemplate
2. 如果下雨，就把 walk / photo 的戶外行程換成 rain 類的
3. 排除前端傳來的 exclude_trip_ids (「搖一搖」時避免重複)
4. 隨機挑一個回傳

未來想加「地理就近排序」或「時段過濾」時，就在這裡擴充。
"""
import random
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trip import TripTemplate
from app.schemas.trip import RecommendRequest, TripPlanResponse


# 下雨時，戶外類的 vibe 自動降級成「躲室內」
RAINY_VIBE_FALLBACK = {"walk", "photo"}


async def recommend(db: AsyncSession, req: RecommendRequest) -> TripPlanResponse:
    """依使用者傳來的 vibe + 天氣挑一個盲盒行程。"""

    vibe = _resolve_vibe(req)

    # 從 DB 撈符合的行程 (不包含使用者剛看過的)
    stmt = select(TripTemplate).where(TripTemplate.vibe_key == vibe)
    if req.exclude_trip_ids:
        stmt = stmt.where(TripTemplate.id.not_in(req.exclude_trip_ids))

    result = await db.execute(stmt)
    candidates = result.scalars().all()

    if not candidates:
        # 排除剛看過的之後沒東西了 → 放寬條件重抽
        result = await db.execute(select(TripTemplate).where(TripTemplate.vibe_key == vibe))
        candidates = result.scalars().all()

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到 vibe={vibe} 的行程",
        )

    chosen = random.choice(candidates)

    return TripPlanResponse(
        id=chosen.id,
        vibe_key=chosen.vibe_key,
        title=chosen.title,
        items=chosen.items,                # Pydantic from_attributes 自動轉換
        generated_at=datetime.now(timezone.utc),
    )


async def get_trip(db: AsyncSession, trip_id: UUID) -> TripPlanResponse:
    """取得單一行程 (分享、歷史查詢用)。"""
    template = await db.get(TripTemplate, trip_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行程不存在")

    return TripPlanResponse(
        id=template.id,
        vibe_key=template.vibe_key,
        title=template.title,
        items=template.items,
        generated_at=template.created_at,
    )


def _resolve_vibe(req: RecommendRequest) -> str:
    """
    決定實際要查哪個 vibe：
    - random → 從所有分類隨機
    - 下雨 + (walk/photo) → 強制改為 rain
    - 其他 → 照傳入
    """
    if req.vibe_key == "random":
        return random.choice(["cafe", "food", "photo", "walk", "gift"])

    # 下雨時避開戶外行程
    rainy = req.weather_condition and req.weather_condition.lower() in {"rain", "thunderstorm", "drizzle"}
    if rainy and req.vibe_key in RAINY_VIBE_FALLBACK:
        return "rain"

    return req.vibe_key
