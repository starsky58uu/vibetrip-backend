"""Google Places 代理 schemas。"""
from typing import Literal

from pydantic import BaseModel, Field

# 對應前端 arData.js 的 CATEGORY_MAP
PlaceCategory = Literal["convenience_store", "cafe", "restaurant", "drink_shop"]


class PlaceResponse(BaseModel):
    place_id: str
    name: str
    latitude: float
    longitude: float
    distance_meters: float | None = None
    rating: float | None = None
    is_open_now: bool | None = None
    categories: list[str] = Field(default_factory=list)
    formatted_address: str | None = None


class PlaceListResponse(BaseModel):
    places: list[PlaceResponse]
