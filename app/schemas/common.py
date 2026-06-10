"""共用 response schemas — 多個端點共用的回傳格式。"""

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """POST /uploads/image 成功回傳。"""

    image_url: str = Field(..., description="可公開存取的圖片 URL")


class UserStatsResponse(BaseModel):
    """GET /users/me/stats — 個人頁統計數字。"""

    spots_count: int = Field(..., ge=0, description="個人足跡總數")
    saved_count: int = Field(..., ge=0, description="收藏的社群地標數")
    days: int = Field(..., ge=0, description="加入天數")


class TasteProfileResponse(BaseModel):
    """GET /taste/profile — AI 口味分析報告。"""

    generated: bool = Field(..., description="是否已呼叫 AI（足跡 < 3 筆時為 false）")
    spots_count: int = Field(..., ge=0, description="納入分析的足跡數")
    headline: str = Field(..., description="主標題（15 字內）")
    subtitle: str = Field(..., description="副標題")
    tags: list[str] = Field(..., description="個性標籤 2～4 個")
    roaming_style: str = Field(..., description="漫遊人格（4～6 字）")
    top_vibes: list[str] = Field(..., description="推薦 vibe 1～2 個")
