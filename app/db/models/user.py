"""
使用者資料表 — 純靜態資料，存 PostgreSQL。
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    # 登入用帳號，唯一
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    # email 也要唯一 (方便未來做忘記密碼)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # bcrypt 雜湊後的密碼 (長度大約 60)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # 顯示名稱，可與 username 不同
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 頭像 URL
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
