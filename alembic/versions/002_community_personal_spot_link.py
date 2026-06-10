"""community_spots.personal_spot_id — 連結個人足跡與社群貼文。

Revision ID: 002_personal_spot
Revises: 001_initial
Create Date: 2026-06-10

對已在 001 之前用 create_all 建庫、缺少此欄位的環境做補丁。
新環境若 001 已含欄位，ADD COLUMN IF NOT EXISTS 為 no-op。
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "002_personal_spot"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        text(
            """
            ALTER TABLE community_spots
            ADD COLUMN IF NOT EXISTS personal_spot_id UUID
            REFERENCES personal_spots(id) ON DELETE CASCADE
            """
        )
    )
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_community_spots_personal_spot_id
            ON community_spots (personal_spot_id)
            WHERE personal_spot_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS uq_community_spots_personal_spot_id"))
    op.execute(text("ALTER TABLE community_spots DROP COLUMN IF EXISTS personal_spot_id"))
