"""認證相關 schemas。"""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserResponse


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr
    display_name: str | None = Field(None, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    """登入/註冊回傳。"""

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # access_token 的秒數


class AccessTokenResponse(BaseModel):
    """refresh 端點只回新的 access_token。"""

    access_token: str
    expires_in: int
    token_type: str = "Bearer"
