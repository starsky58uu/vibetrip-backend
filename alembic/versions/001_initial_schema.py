"""啟用 PostGIS 並建立所有 ORM 資料表。

Revision ID: 001_initial
Revises:
Create Date: 2026-06-10

新環境：直接 upgrade。
既有環境（曾用 create_all）：先 `alembic stamp 001_initial` 再 upgrade 002。
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.db.base import Base
from app.db.models import (  # noqa: F401 — 註冊 metadata
    BusStop,
    CommunitySpot,
    MrtStation,
    PersonalSpot,
    SpotLike,
    SpotSave,
    TripItem,
    TripTemplate,
    User,
    YoubikeStation,
)

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
    op.execute(text("DROP EXTENSION IF EXISTS postgis"))
