"""AI 口味分析端點 — 依個人足跡生成漫遊人格報告。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.db.models.user import User
from app.schemas.common import TasteProfileResponse
from app.services import taste_service

router = APIRouter()


@router.get("/profile", response_model=TasteProfileResponse)
async def get_taste_profile(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh: Annotated[bool, Query(description="true = 跳過快取，強制重新生成")] = False,
) -> TasteProfileResponse:
    """
    AI 分析使用者的城市漫遊足跡，生成個性化口味報告。

    - 足跡不足 3 筆時回傳引導文案（generated: false）
    - 3 筆以上呼叫 Groq LLaMA 3.3 生成報告（generated: true）
    - 結果快取 12 小時；?refresh=true 強制重新生成
    """
    data = await taste_service.get_taste_profile(db, user.id, refresh=refresh)
    return TasteProfileResponse.model_validate(data)
