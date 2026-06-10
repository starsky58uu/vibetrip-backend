"""盲盒行程 schemas。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 心情分類 — 跟前端 vibe_key 一對一對應
VibeKey = Literal["cafe", "food", "photo", "rain", "walk", "gift", "random"]


class RecommendRequest(BaseModel):
    vibe_key: VibeKey = Field(..., description="心情分類 (random = 後端自己挑)")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    weather_condition: str | None = Field(
        None, description="OpenWeatherMap 的 main 欄位，下雨時會避開戶外行程"
    )
    exclude_trip_ids: list[UUID] = Field(
        default_factory=list, description="「搖一搖重抽」時排除剛看過的"
    )


class TripItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: str
    activity: str
    desc: str
    dur: str | None = None
    tag: str | None = None
    dist: str | None = None
    mood: str | None = None


class TripPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vibe_key: str
    title: str
    subtitle: str | None = None
    items: list[TripItemResponse]
    generated_at: datetime
