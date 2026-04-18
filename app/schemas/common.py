"""
通用 Pydantic schemas — 座標、分頁等跨模組共用的型別。
"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Coordinate(BaseModel):
    """WGS84 座標。"""

    latitude: float = Field(..., ge=-90, le=90, description="緯度")
    longitude: float = Field(..., ge=-180, le=180, description="經度")


class Pagination(BaseModel):
    """cursor-based 分頁資訊。"""

    next_cursor: str | None = None
    has_more: bool = False


class Page(BaseModel, Generic[T]):
    """分頁回應的外殼。用法：Page[SpotResponse]。"""

    data: list[T]
    pagination: Pagination
