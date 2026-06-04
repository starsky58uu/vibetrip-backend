"""使用者自身資料端點。"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.db.models.spot import PersonalSpot, SpotSave
from app.db.models.user import User
from app.schemas.user import UserResponse, UserUpdateRequest

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    """取得目前登入者的資料。"""
    return UserResponse.model_validate(user)


@router.get("/me/stats")
async def get_me_stats(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """取得使用者統計數字：足跡數、收藏數、加入天數。"""
    spots_count = await db.scalar(
        select(func.count()).select_from(PersonalSpot).where(PersonalSpot.owner_id == user.id)
    ) or 0

    saved_count = await db.scalar(
        select(func.count()).select_from(SpotSave).where(SpotSave.user_id == user.id)
    ) or 0

    created = user.created_at
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - created).days if created else 0

    return {
        "spots_count": spots_count,
        "saved_count": saved_count,
        "days": days,
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    req: UserUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """更新自己的個人資料 (目前支援 display_name / avatar_url)。"""
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.avatar_url is not None:
        user.avatar_url = req.avatar_url

    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)
