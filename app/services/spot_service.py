"""
足跡服務層 — 個人足跡與社群地標。

- 個人足跡：`is_public=True` 時會建立連結的 `CommunitySpot`（`personal_spot_id`）
- 社群列表：排序與距離交給 PostGIS SQL
- 按讚 / 收藏：`INSERT ON CONFLICT` + 原子 `UPDATE` 計數
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor
from app.db.models.spot import CommunitySpot, PersonalSpot, SpotLike, SpotSave
from app.db.models.user import User
from app.schemas.spot import (
    CommunitySpotResponse,
    CursorPagination,
    PaginatedCommunitySpotsResponse,
    PersonalSpotCreateRequest,
    PersonalSpotResponse,
    PersonalSpotUpdateRequest,
    SpotAuthor,
    ToggleLikeResponse,
    ToggleSaveResponse,
    ViewerState,
)


def _point(lon: float, lat: float):
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(type_=PersonalSpot.location.type)


async def _coords_for_spot(db: AsyncSession, spot_id: UUID) -> tuple[float, float]:
    row = (
        await db.execute(
            text(
                "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
                "FROM personal_spots WHERE id = :id"
            ),
            {"id": spot_id},
        )
    ).one()
    return row.lat, row.lon


async def _linked_community(db: AsyncSession, personal_spot_id: UUID) -> CommunitySpot | None:
    result = await db.execute(
        select(CommunitySpot).where(CommunitySpot.personal_spot_id == personal_spot_id)
    )
    return result.scalar_one_or_none()


async def _sync_community_from_personal(
    db: AsyncSession,
    spot: PersonalSpot,
    lat: float,
    lon: float,
) -> None:
    """依 is_public 建立、更新或移除連結的社群貼文。"""
    community = await _linked_community(db, spot.id)
    if spot.is_public:
        if community is None:
            db.add(
                CommunitySpot(
                    personal_spot_id=spot.id,
                    author_id=spot.owner_id,
                    location=_point(lon, lat),
                    content=spot.note,
                    image_url=spot.image_url,
                )
            )
        else:
            community.content = spot.note
            community.image_url = spot.image_url
    elif community is not None:
        await db.delete(community)


# ==========================================================================
# 個人足跡
# ==========================================================================
async def create_personal_spot(
    db: AsyncSession,
    owner: User,
    req: PersonalSpotCreateRequest,
) -> PersonalSpotResponse:
    spot = PersonalSpot(
        owner_id=owner.id,
        location=_point(req.longitude, req.latitude),
        note=req.note,
        image_url=req.image_url,
        is_public=req.is_public,
    )
    db.add(spot)
    await db.flush()

    if req.is_public:
        db.add(
            CommunitySpot(
                personal_spot_id=spot.id,
                author_id=owner.id,
                location=_point(req.longitude, req.latitude),
                content=req.note,
                image_url=req.image_url,
            )
        )

    await db.commit()
    await db.refresh(spot)
    return _spot_to_response(spot, req.latitude, req.longitude)


async def list_personal_spots(
    db: AsyncSession,
    owner: User,
) -> list[PersonalSpotResponse]:
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
    db: AsyncSession,
    owner: User,
    spot_id: UUID,
    req: PersonalSpotUpdateRequest,
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

    lat, lon = await _coords_for_spot(db, spot.id)
    await _sync_community_from_personal(db, spot, lat, lon)

    await db.commit()
    await db.refresh(spot)
    return _spot_to_response(spot, lat, lon)


async def delete_personal_spot(db: AsyncSession, owner: User, spot_id: UUID) -> None:
    spot = await db.get(PersonalSpot, spot_id)
    if spot is None or spot.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="足跡不存在")
    # 連結的 CommunitySpot 會因 personal_spot_id FK CASCADE 一併刪除
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
    cursor: str | None = None,
) -> PaginatedCommunitySpotsResponse:
    fetch_limit = limit + 1
    cursor_filter = ""
    dist_select = ""

    params: dict = {
        "viewer_id": viewer.id if viewer else None,
        "limit": fetch_limit,
        "lat": lat,
        "lon": lon,
    }

    if sort == "popular":
        order_clause = "ORDER BY cs.likes_count DESC, cs.created_at DESC, cs.id DESC"
        if cursor:
            c = decode_cursor(cursor)
            cursor_filter = (
                "AND (cs.likes_count, cs.created_at, cs.id) < "
                "(:c_likes, :c_created_at::timestamptz, :c_id::uuid)"
            )
            params.update(
                {
                    "c_likes": c["likes_count"],
                    "c_created_at": c["created_at"],
                    "c_id": c["id"],
                }
            )
    elif sort == "nearby":
        if lat is None or lon is None:
            raise HTTPException(status_code=400, detail="nearby 排序需提供 lat/lon")
        dist_select = (
            ", cs.location <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS dist_m"
        )
        order_clause = "ORDER BY dist_m ASC, cs.id ASC"
        if cursor:
            c = decode_cursor(cursor)
            cursor_filter = "AND (dist_m, id) > (:c_dist_m, :c_id::uuid)"
            params.update({"c_dist_m": c["dist_m"], "c_id": c["id"]})
        inner_query = f"""
        SELECT
            cs.id, cs.content, cs.image_url, cs.likes_count, cs.saves_count, cs.created_at,
            ST_Y(cs.location::geometry) AS lat,
            ST_X(cs.location::geometry) AS lon,
            u.id AS author_id, u.username, u.display_name, u.avatar_url,
            CASE WHEN sl.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_liked,
            CASE WHEN ss.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_saved
            {dist_select}
        FROM community_spots cs
        JOIN users u ON u.id = cs.author_id
        LEFT JOIN spot_likes sl ON sl.spot_id = cs.id AND sl.user_id = :viewer_id
        LEFT JOIN spot_saves ss ON ss.spot_id = cs.id AND ss.user_id = :viewer_id
        """
        query = f"""
        SELECT * FROM ({inner_query}) AS nearby_page
        WHERE 1=1 {cursor_filter}
        {order_clause}
        LIMIT :limit
        """
        rows = (await db.execute(text(query), params)).mappings().all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = encode_cursor({"dist_m": last["dist_m"], "id": str(last["id"])})
        return PaginatedCommunitySpotsResponse(
            data=[_row_to_community(r) for r in page_rows],
            pagination=CursorPagination(next_cursor=next_cursor, has_more=has_more),
        )
    else:
        order_clause = "ORDER BY cs.created_at DESC, cs.id DESC"
        if cursor:
            c = decode_cursor(cursor)
            cursor_filter = "AND (cs.created_at, cs.id) < (:c_created_at::timestamptz, :c_id::uuid)"
            params.update({"c_created_at": c["created_at"], "c_id": c["id"]})

    query = f"""
        SELECT
            cs.id, cs.content, cs.image_url, cs.likes_count, cs.saves_count, cs.created_at,
            ST_Y(cs.location::geometry) AS lat,
            ST_X(cs.location::geometry) AS lon,
            u.id AS author_id, u.username, u.display_name, u.avatar_url,
            CASE WHEN sl.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_liked,
            CASE WHEN ss.user_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_saved
            {dist_select}
        FROM community_spots cs
        JOIN users u ON u.id = cs.author_id
        LEFT JOIN spot_likes sl ON sl.spot_id = cs.id AND sl.user_id = :viewer_id
        LEFT JOIN spot_saves ss ON ss.spot_id = cs.id AND ss.user_id = :viewer_id
        WHERE 1=1 {cursor_filter}
        {order_clause}
        LIMIT :limit
    """
    rows = (await db.execute(text(query), params)).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        if sort == "popular":
            next_cursor = encode_cursor(
                {
                    "likes_count": last["likes_count"],
                    "created_at": last["created_at"],
                    "id": str(last["id"]),
                }
            )
        elif sort == "nearby":
            next_cursor = encode_cursor({"dist_m": last["dist_m"], "id": str(last["id"])})
        else:
            next_cursor = encode_cursor({"created_at": last["created_at"], "id": str(last["id"])})

    return PaginatedCommunitySpotsResponse(
        data=[_row_to_community(r) for r in page_rows],
        pagination=CursorPagination(next_cursor=next_cursor, has_more=has_more),
    )


async def list_saved_spots(db: AsyncSession, viewer: User) -> list[CommunitySpotResponse]:
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
    return [_row_to_community(r, is_saved=True) for r in rows]


def _row_to_community(r, is_saved: bool | None = None) -> CommunitySpotResponse:
    saved = r["is_saved"] if is_saved is None else is_saved
    return CommunitySpotResponse(
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
        viewer_state=ViewerState(is_liked=r["is_liked"], is_saved=saved),
    )


async def toggle_like(db: AsyncSession, user: User, spot_id: UUID) -> ToggleLikeResponse:
    """按讚 / 取消讚 — 用 INSERT ON CONFLICT + 原子 UPDATE 避免計數漂移。"""
    if await db.get(CommunitySpot, spot_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地標不存在")

    inserted = await db.execute(
        insert(SpotLike).values(user_id=user.id, spot_id=spot_id).on_conflict_do_nothing()
    )
    if inserted.rowcount:
        result = await db.execute(
            update(CommunitySpot)
            .where(CommunitySpot.id == spot_id)
            .values(likes_count=CommunitySpot.likes_count + 1)
            .returning(CommunitySpot.likes_count)
        )
        likes_count = result.scalar_one()
        await db.commit()
        return ToggleLikeResponse(is_liked=True, likes_count=likes_count)

    deleted = await db.execute(
        delete(SpotLike).where(
            SpotLike.user_id == user.id,
            SpotLike.spot_id == spot_id,
        )
    )
    if deleted.rowcount:
        result = await db.execute(
            update(CommunitySpot)
            .where(CommunitySpot.id == spot_id)
            .values(likes_count=func.greatest(CommunitySpot.likes_count - 1, 0))
            .returning(CommunitySpot.likes_count)
        )
        likes_count = result.scalar_one()
    else:
        spot = await db.get(CommunitySpot, spot_id)
        likes_count = spot.likes_count if spot else 0

    await db.commit()
    return ToggleLikeResponse(is_liked=False, likes_count=likes_count)


async def toggle_save(db: AsyncSession, user: User, spot_id: UUID) -> ToggleSaveResponse:
    """收藏 / 取消收藏 — 同上。"""
    if await db.get(CommunitySpot, spot_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="地標不存在")

    inserted = await db.execute(
        insert(SpotSave).values(user_id=user.id, spot_id=spot_id).on_conflict_do_nothing()
    )
    if inserted.rowcount:
        result = await db.execute(
            update(CommunitySpot)
            .where(CommunitySpot.id == spot_id)
            .values(saves_count=CommunitySpot.saves_count + 1)
            .returning(CommunitySpot.saves_count)
        )
        saves_count = result.scalar_one()
        await db.commit()
        return ToggleSaveResponse(is_saved=True, saves_count=saves_count)

    deleted = await db.execute(
        delete(SpotSave).where(
            SpotSave.user_id == user.id,
            SpotSave.spot_id == spot_id,
        )
    )
    if deleted.rowcount:
        result = await db.execute(
            update(CommunitySpot)
            .where(CommunitySpot.id == spot_id)
            .values(saves_count=func.greatest(CommunitySpot.saves_count - 1, 0))
            .returning(CommunitySpot.saves_count)
        )
        saves_count = result.scalar_one()
    else:
        spot = await db.get(CommunitySpot, spot_id)
        saves_count = spot.saves_count if spot else 0

    await db.commit()
    return ToggleSaveResponse(is_saved=False, saves_count=saves_count)
