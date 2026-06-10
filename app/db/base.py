"""
SQLAlchemy Base 類別 + 共用的欄位 mixin。

所有 ORM models 都繼承自 Base；Base.metadata 會記錄全部 table，
讓我們可以用一次 metadata.create_all() 一次建好。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 的 root。"""

    pass


class UUIDPrimaryKey:
    """
    Mixin：主鍵用 UUID v4。
    不用自增 int，避免前端猜 id。
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


def utcnow() -> datetime:
    """統一的 UTC now()，保證有時區資訊。"""
    return datetime.now(UTC)


class TimestampMixin:
    """
    Mixin：建立時間 + 更新時間。
    DB 層用 timestamptz (含時區)，避免跨時區 bug。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,  # 每次 UPDATE 會自動刷新
        nullable=False,
    )
