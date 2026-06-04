"""
足跡服務層 — 個人 + 社群。

PostGIS 用法：
- 儲存：把 (lng, lat) 包成 POINT 存進 location 欄位
- 查詢附近：用 ST_DWithin / ST_Distance

"本地排序與過濾交給 SQL，讓 Python 只做 orm → pydantic 的轉換。"
"""
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.spot import CommunitySpot, PersonalSpot, SpotLike, SpotSave
from app.db.models.user import User
from app.schemas.spot import (
    CommunitySpotResponse,
    PersonalSpotCreateRequest,
    PersonalSpotResponse,
    PersonalSpotUpdateRequest,
    SpotAuthor,
    ToggleLikeResponse,
    ToggleSaveResponse,
    ViewerState,
)


# ==========================================================================
# 個人足跡
# ==========================================================================
def _point(lon: float, lat: float):
    """座標轉成 PostGIS geography point — Python 這邊唯一跟地理相關的工具函式。"""
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(
        type_=PersonalSpot.location.type
    )


async def create_personal_spot(
    db: AsyncSession, owner: User, req: PersonalSpotCreateRequest,
) -> PersonalSpotResponse:
    spot = PersonalSpot(
        owner_id=owner.id,
        location=_point(req.longitude, req.latitude),
        note=req.note,
        image_url=req.image_url,
        is_public=req.is_public,
    )
    db.add(spot)

    # 若選擇公開，同時產生一筆 CommunitySpot 分享給大家看
    if req.is_public:
        db.add(CommunitySpot(
            author_id=owner.id,
            location=_point(req.longitude, req.latitude),
            content=req.note,
            image_url=req.image_url,
        ))

    await db.commit()
    await db.refresh(spot)
    return _spot_to_response(spot, req.latitude, req.longitude)


async def list_personal_spots(
    db: AsyncSession, owner: User,
) -> list[PersonalSpotResponse]:
    """列出使用者所有私人足跡。"""
    stmt = text(
        """
        SELECT id, owner_id, note, image_url, is_public, created_at, updated_at,
               ST_Y(location::geometry) AS lat,
               ST_X(location::geometry) AS lon
        FROM personal_spots
        WHERE owner_id = :owner
        ORDER BY created_at DESC
        """
    )
    rows = (await db.execute(stmt, {"owner": owner.id})).mappings().all()
    return [
        PersonalSpotResponse(
            id=r["id"],
            owner_id=r["owner_id"],
            latitude=r["lat"],
            longitude=r["lon"],
            note=r["note"],
            image_url=r["image_url"],
            is_public=r["is_public"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def update_personal_spot(
    db: AsyncSession, owner: User, spot_id: UUID, req: PersonalSpotUpdateRequest,
) -> PersonalSpotResponse:
    spot = await db.get(PersonalSpot, spot_id)
    if spot is None or spot.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="足跡不存在")

    if req.note is not None:
        spot.note = req.note
    if req.image_url is not None:
        spot.image_url = req.image_url
    if req.is_public is not None:
        spot.is_public = req.is_public

    await db.commit()
    await db.refresh(spot)

    # 用個 raw 查詢把 lat/lon 取回來
    coord = await db.execute(
        text("SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon FROM personal_spots WHERE id = :id"),
        {"id": spot.id},
    )
    c = coord.one()
    return _spot_to_response(spot, c.lat, c.lon)


async def delete_personal_spot(db: AsyncSession, owner: User, spot_id: UUID) -> None:
    spot = await db.get(PersonalSpot, spot_id)
    if spot is None or spot.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="足跡不存在")
    await db.delete(spot)
    await db.commit()


def _spot_to_response(spot: PersonalSpot, lat: float, lon: float) -> PersonalSpotResponse:
    return PersonalSpotResponse(
        id=spot.id,
        owner_id=spot.owner_id,
        latitude=lat,
        longitude=lon,
        note=spot.note,
        image_url=spot.image_url,
        is_public=spot.is_public,
        created_at=spot.created_at,
        updated_at=spot.updated_at,
    )


# ==========================================================================
# 社群足跡
# ==========================================================================
async def list_community_spots(
    db: AsyncSession,
    viewer: User | None,
    sort: str = "recent",
    lat: float | None = None,
    lon: float | None = None,
    limit: int = 20,
) -> list[CommunitySpotResponse]:
    """
    列出社群地標。
    sort:
      - recent: 依建立時間倒序
      - popular: 依讚數倒序
      - nearby: 依距離 (需傳 lat/lon)
    """

    order_clause = "ORDER BY cs.created_at DESC"
    if sort == "popular":
        order_clause = "ORDER BY cs.likes_count DESC, cs.created_at DESC"
    elif sort == "nearby":
        if lat is None or lon is None:
            raise HTTPException(status_code=400, detail="nearby 排序需提供 lat/lon")
        order_clause = "ORDER BY cs.location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"

    # 一次撈 spot 和作者資訊，再 LEFT JOIN viewer 的 like/save 狀態
    query = f"""
        SELECT
            cs.id, cs.content, cs.image_url, cs.likes_count, cs.saves_count, cs.created_at,
            ST_Y(cs.location::geometry) AS lat,
            ST_X(cs.location::geometry) AS lon,
            u.id AS author_id, u.username, u.display_name, u.avatar_url,
            CASE WHEN sl.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_liked,
            CASE WHEN ss.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_saved
        FROM community_spots cs
        JOIN users u ON u.id = cs.author_id
        LEFT JOIN spot_likes sl ON sl.spot_id = cs.id AND sl.user_id = :viewer_id
        LEFT JOIN spot_saves ss ON ss.spot_id = cs.id AND ss.user_id = :viewer_id
        {order_clause}
        LIMIT :limit
    """

    params = {
        "viewer_id": viewer.id if viewer else None,
        "limit": limit,
        "lat": lat,
        "lon": lon,
    }
    rows = (await db.execute(text(query), params)).mappings().all()

    return [
        CommunitySpotResponse(
            id=r["id"],
            author=SpotAuthor(
                id=r["author_id"],
                username=r["username"],
                display_name=r["display_name"],
                avatar_url=r["avatar_url"],
            ),
            latitude=r["lat"],
            longitude=r["lon"],
            content=r["content"],
            image_url=r["image_url"],
            likes_count=r["likes_count"],
            saves_count=r["saves_count"],
            created_at=r["created_at"],
            viewer_state=ViewerState(is_liked=r["is_liked"], is_saved=r["is_saved"]),
        )
        for r in rows
    ]


async def list_saved_spots(db: AsyncSession, viewer: User) -> list[CommunitySpotResponse]:
    """列出使用者收藏的社群地標。"""
    query = """
        SELECT
            cs.id, cs.content, cs.image_url, cs.likes_count, cs.saves_count, cs.created_at,
            ST_Y(cs.location::geometry) AS lat,
            ST_X(cs.location::geometry) AS lon,
            u.id AS author_id, u.username, u.display_name, u.avatar_url,
            CASE WHEN sl.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_liked
        FROM spot_saves ss
        JOIN community_spots cs ON cs.id = ss.spot_id
        JOIN users u ON u.id = cs.author_id
        LEFT JOIN spot_likes sl ON sl.spot_id = cs.id AND sl.user_id = :viewer_id
        WHERE ss.user_id = :viewer_id
        ORDER BY cs.created_at DESC
    """
    rows = (await db.execute(text(query), {"viewer_id": viewer.id})).mappings().all()
    return [
        CommunitySpotResponse(
            id=r["id"],
            author=SpotAuthor(
                id=r["author_id"],
                username=r["username"],
                display_name=r["display_name"],
                avatar_url=r["avatar_url"],
            ),
            latitude=r["lat"],
            longitude=r["lon"],
            content=r["content"],
            image_url=r["image_url"],
            likes_count=r["likes_count"],
            saves_count=r["saves_count"],
            created_at=r["created_at"],
            viewer_state=ViewerState(is_liked=r["is_liked"], is_saved=True),
        )
        for r in rows
    ]


async def toggle_like(db: AsyncSession, user: User, spot_id: UUID) -> ToggleLikeResponse:
    """按讚 / 取消讚 (toggle 語義)。"""
    spot = await db.get(CommunitySpot, spot_id)
    if spot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地標不存在")

    existing = await db.get(SpotLike, (user.id, spot_id))

    if existing:
        await db.delete(existing)
        spot.likes_count = max(0, spot.likes_count - 1)
        is_liked = False
    else:
        db.add(SpotLike(user_id=user.id, spot_id=spot_id))
        spot.likes_count += 1
        is_liked = True

    await db.commit()
    return ToggleLikeResponse(is_liked=is_liked, likes_count=spot.likes_count)


async def toggle_save(db: AsyncSession, user: User, spot_id: UUID) -> ToggleSaveResponse:
    """收藏 / 取消收藏。"""
    spot = await db.get(CommunitySpot, spot_id)
    if spot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地標不存在")

    existing = await db.get(SpotSave, (user.id, spot_id))

    if existing:
        await db.delete(existing)
        spot.saves_count = max(0, spot.saves_count - 1)
        is_saved = False
    else:
        db.add(SpotSave(user_id=user.id, spot_id=spot_id))
        spot.saves_count += 1
        is_saved = True

    await db.commit()
    return ToggleSaveResponse(is_saved=is_saved, saves_count=spot.saves_count)
