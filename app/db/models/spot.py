"""
足跡相關 models — 使用 PostGIS 的 GEOGRAPHY(POINT) 儲存座標。

為什麼用 GEOGRAPHY 而不是 GEOMETRY？
- GEOGRAPHY 是球面座標，算距離就是真實的「公尺」
- GEOMETRY 是平面座標，得自己處理投影轉換
對我們「找最近的咖啡廳」這種需求，GEOGRAPHY 才對。

常用查詢：
  SELECT *, ST_Distance(location, :origin) AS d
  FROM personal_spots
  WHERE ST_DWithin(location, :origin, 500)   -- 500 公尺內
  ORDER BY d
  LIMIT 20;
全部交給 PostGIS 算，Python 不用寫半行距離邏輯。
"""

from typing import Any
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class PersonalSpot(Base, UUIDPrimaryKey, TimestampMixin):
    """使用者的私人足跡 (對應前端 MapScreen 的 mySpots)。"""

    __tablename__ = "personal_spots"

    owner_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # PostGIS 空間欄位：POINT 代表 (lng, lat)，srid 4326 = WGS84
    # spatial_index=True 會自動建 GIST 索引，空間查詢才快
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 若 is_public=True 則同時產生一筆 CommunitySpot 分享給大家看
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CommunitySpot(Base, UUIDPrimaryKey, TimestampMixin):
    """社群地標 — 其他人可以看到、按讚、收藏。"""

    __tablename__ = "community_spots"

    # 若由個人足跡公開而來，用此欄位連結（刪除個人足跡時 CASCADE 一併移除）
    personal_spot_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("personal_spots.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )

    author_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 讚數 / 收藏數：實際寫 SpotLike / SpotSave 時用 trigger 或 service 層同步更新
    # (這樣前端列表不用每次都 COUNT)
    likes_count: Mapped[int] = mapped_column(default=0, nullable=False)
    saves_count: Mapped[int] = mapped_column(default=0, nullable=False)


class SpotLike(Base):
    """
    中間表：誰對哪個社群地標按過讚。
    複合主鍵 (user_id, spot_id) 確保同一個人對同一個 spot 只能按一次。
    """

    __tablename__ = "spot_likes"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    spot_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("community_spots.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        # 查「某使用者按過讚的全部 spot」常用，建索引
        Index("ix_spot_likes_user", "user_id"),
    )


class SpotSave(Base):
    """收藏 (同上，另一張表以示語義區別)。"""

    __tablename__ = "spot_saves"

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    spot_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("community_spots.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (Index("ix_spot_saves_user", "user_id"),)
