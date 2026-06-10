"""
盲盒行程模板 — 從前端的 mockData.js 搬過來。

結構：
- TripTemplate (一個行程，有標題、心情分類)
- TripItem (行程中的一個活動，依 order_index 排序)

每次呼叫 POST /trips/recommend 時，後端會根據 vibe 隨機挑一個 Template 回傳。
"""

from sqlalchemy import UUID, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class TripTemplate(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "trip_templates"

    # 心情分類：cafe / food / photo / rain / walk / gift
    vibe_key: Mapped[str] = mapped_column(String(32), index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(64), nullable=False)

    # 一個 Template 有多個 Item，依 order_index 排序
    items: Mapped[list["TripItem"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TripItem.order_index",
        lazy="selectin",  # 取 template 時自動 JOIN items，避免 N+1
    )


class TripItem(Base, UUIDPrimaryKey):
    __tablename__ = "trip_items"

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 行程順序，從 0 開始
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # HH:MM 格式，例如 "13:30"
    time: Mapped[str] = mapped_column(String(5), nullable=False)

    # 地點名稱：星巴克、大安森林公園...
    activity: Mapped[str] = mapped_column(String(64), nullable=False)

    # 一句話描述
    desc: Mapped[str] = mapped_column(Text, nullable=False)

    # Ionicons 的 icon 名稱：cafe / restaurant / walk ...
    icon: Mapped[str] = mapped_column(String(32), nullable=False)

    # 前端用的主題色 (hex)
    color: Mapped[str] = mapped_column(String(7), nullable=False)

    template: Mapped["TripTemplate"] = relationship(back_populates="items")
