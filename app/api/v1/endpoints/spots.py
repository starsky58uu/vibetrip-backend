"""足跡端點 — 個人 + 社群。"""
from typing import Annotated, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, get_optional_user
from app.db.models.user import User
from app.schemas.spot import (
    CommunitySpotResponse,
    PersonalSpotCreateRequest,
    PersonalSpotResponse,
    PersonalSpotUpdateRequest,
    ToggleLikeResponse,
    ToggleSaveResponse,
)
from app.services import spot_service

router = APIRouter()


# ==========================================================================
# 個人足跡 (全部需要登入)
# ==========================================================================
@router.post("/personal", response_model=PersonalSpotResponse, status_code=201)
async def create_personal(
    req: PersonalSpotCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonalSpotResponse:
    """新增個人足跡 (前端長按地圖)。"""
    return await spot_service.create_personal_spot(db, user, req)


@router.get("/personal", response_model=list[PersonalSpotResponse])
async def list_personal(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PersonalSpotResponse]:
    """列出自己所有足跡。"""
    return await spot_service.list_personal_spots(db, user)


@router.patch("/personal/{spot_id}", response_model=PersonalSpotResponse)
async def update_personal(
    spot_id: UUID,
    req: PersonalSpotUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PersonalSpotResponse:
    """編輯個人足跡。"""
    return await spot_service.update_personal_spot(db, user, spot_id, req)


@router.delete("/personal/{spot_id}", status_code=204)
async def delete_personal(
    spot_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """刪除個人足跡。"""
    await spot_service.delete_personal_spot(db, user, spot_id)


# ==========================================================================
# 社群地標 (可匿名瀏覽，互動需登入)
# ==========================================================================
@router.get("/saved", response_model=list[CommunitySpotResponse])
async def list_saved(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CommunitySpotResponse]:
    """列出目前使用者收藏的社群地標。"""
    return await spot_service.list_saved_spots(db, user)


@router.get("/community", response_model=list[CommunitySpotResponse])
async def list_community(
    db: Annotated[AsyncSession, Depends(get_db)],
    viewer: Annotated[Optional[User], Depends(get_optional_user)],
    sort: Annotated[Literal["recent", "popular", "nearby"], Query()] = "recent",
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[CommunitySpotResponse]:
    """瀏覽社群地標。匿名也能看，登入的話會填入 is_liked / is_saved。"""
    return await spot_service.list_community_spots(db, viewer, sort, lat, lon, limit)


@router.post("/community/{spot_id}/like", response_model=ToggleLikeResponse)
async def like_spot(
    spot_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToggleLikeResponse:
    """按讚 / 取消讚 (toggle)。"""
    return await spot_service.toggle_like(db, user, spot_id)


@router.post("/community/{spot_id}/save", response_model=ToggleSaveResponse)
async def save_spot(
    spot_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToggleSaveResponse:
    """收藏 / 取消收藏 (toggle)。"""
    return await spot_service.toggle_save(db, user, spot_id)
