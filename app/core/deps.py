"""
FastAPI 依賴注入集中處。

在 endpoint 裡：
    @router.get("/me")
    async def me(user: User = Depends(get_current_user)):
        ...

這些依賴最常用的就是「取目前登入的使用者」。
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.db.models.user import User


# tokenUrl：Swagger UI 用，指到我們的 login endpoint
# auto_error=False：讓我們能做「選擇性登入」(公開端點也能看使用者資料)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    必須登入才能用的端點，用這個依賴。
    Token 錯誤或使用者不存在都回 401。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未通過身份驗證",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    try:
        user_id: UUID = decode_token(token, expected_type="access")
    except JWTError:
        raise credentials_exception

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_optional_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """
    選擇性登入 (用在社群地標這類公開列表端點)：
    - 有 token 且有效：回使用者，可用於填 viewer_state.is_liked
    - 沒 token 或 token 壞掉：回 None，不拋錯
    """
    if token is None:
        return None
    try:
        user_id = decode_token(token, expected_type="access")
        return await db.get(User, user_id)
    except JWTError:
        return None
