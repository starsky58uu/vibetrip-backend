"""使用者 schemas。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """回給前端的使用者資料 — 絕對不包含密碼！"""

    model_config = ConfigDict(from_attributes=True)  # 讓 ORM → Pydantic 自動對應

    id: UUID
    username: str
    email: str
    display_name: str | None
    avatar_url: str | None
    created_at: datetime


class UserUpdateRequest(BaseModel):
    """PATCH /users/me 用，全部欄位可選。"""

    display_name: str | None = None
    avatar_url: str | None = None
