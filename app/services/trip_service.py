"""
盲盒行程服務層。

優先呼叫 `ai_service.generate_trip`；失敗時從 DB `TripTemplate` 隨機挑一筆。
`vibe_key=random` 或下雨時會調整實際查詢的 vibe。
注意：AI 產生的 `id` 不寫入 DB，`GET /trips/{id}` 僅適用 seed 模板。
"""

import logging
import random
import uuid
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trip import TripTemplate
from app.schemas.trip import RecommendRequest, TripPlanResponse
from app.services.ai_service import generate_trip

logger = logging.getLogger(__name__)

# 下雨時，戶外類的 vibe 自動降級成「躲室內」
RAINY_VIBE_FALLBACK = {"walk", "photo"}


async def recommend(db: AsyncSession, req: RecommendRequest) -> TripPlanResponse:
    """依使用者傳來的 vibe + 天氣挑一個盲盒行程。"""

    vibe = _resolve_vibe(req)

    try:
        # 優先用 AI 生成
        ai_result = await generate_trip(
            vibe_key=vibe,
            lat=req.latitude,
            lon=req.longitude,
            weather=req.weather_condition,
            exclude_trip_ids=req.exclude_trip_ids or None,
        )
        return TripPlanResponse(
            id=uuid.uuid4(),
            vibe_key=vibe,
            title=ai_result["title"],
            subtitle=ai_result.get("subtitle", ""),
            items=ai_result["items"],
            generated_at=datetime.now(UTC),
        )
    except Exception:
        logger.exception("AI 行程生成失敗，改用 DB 模板")
        return await _recommend_from_db(db, vibe, req.exclude_trip_ids)


async def get_trip(db: AsyncSession, trip_id: UUID) -> TripPlanResponse:
    """
    取得單一行程（分享、歷史查詢用）。

    僅回傳 DB 中的 TripTemplate（seed 模板）。
    POST /trips/recommend 由 AI 產生的行程 ID 不會寫入 DB，因此無法用此端點查詢。
    """
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
    rainy = req.weather_condition and req.weather_condition.lower() in {
        "rain",
        "thunderstorm",
        "drizzle",
    }
    if rainy and req.vibe_key in RAINY_VIBE_FALLBACK:
        return "rain"

    return req.vibe_key


async def _recommend_from_db(db, vibe, exclude_ids):
    stmt = select(TripTemplate).where(TripTemplate.vibe_key == vibe)
    if exclude_ids:
        stmt = stmt.where(TripTemplate.id.not_in(exclude_ids))
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    if not candidates:
        result = await db.execute(select(TripTemplate).where(TripTemplate.vibe_key == vibe))
        candidates = result.scalars().all()
    if not candidates:
        raise HTTPException(status_code=404, detail=f"找不到 vibe={vibe} 的行程")
    chosen = random.choice(candidates)
    return TripPlanResponse(
        id=chosen.id,
        vibe_key=chosen.vibe_key,
        title=chosen.title,
        items=chosen.items,
        generated_at=datetime.now(UTC),
    )
