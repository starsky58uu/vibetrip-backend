"""足跡 schemas — 個人 + 社群。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- 個人足跡 ----------
class PersonalSpotCreateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    note: str = Field("", max_length=500)
    image_url: str | None = None
    is_public: bool = False


class PersonalSpotUpdateRequest(BaseModel):
    note: str | None = Field(None, max_length=500)
    image_url: str | None = None
    is_public: bool | None = None


class PersonalSpotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    latitude: float
    longitude: float
    note: str
    image_url: str | None
    is_public: bool
    created_at: datetime
    updated_at: datetime


# ---------- 社群足跡 ----------
class SpotAuthor(BaseModel):
    """社群貼文的作者摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str | None
    avatar_url: str | None


class ViewerState(BaseModel):
    """目前瀏覽者對這個 spot 的互動狀態。"""

    is_liked: bool = False
    is_saved: bool = False


class CommunitySpotResponse(BaseModel):
    id: UUID
    author: SpotAuthor
    latitude: float
    longitude: float
    content: str
    image_url: str | None
    likes_count: int
    saves_count: int
    created_at: datetime
    viewer_state: ViewerState


# ---------- 互動 ----------
class ToggleLikeResponse(BaseModel):
    is_liked: bool
    likes_count: int


class ToggleSaveResponse(BaseModel):
    is_saved: bool
    saves_count: int


class CursorPagination(BaseModel):
    next_cursor: str | None = None
    has_more: bool


class PaginatedCommunitySpotsResponse(BaseModel):
    data: list[CommunitySpotResponse]
    pagination: CursorPagination
