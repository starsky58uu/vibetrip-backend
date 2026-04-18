"""
安全相關工具：密碼雜湊 + JWT Token 簽發/驗證。

- 密碼：用 bcrypt 雜湊，絕對不存明文
- Token：用 HS256 簽名的 JWT，claim 裡放 user_id 與 token 類型 (access/refresh)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# ---------- 密碼雜湊 ----------
# schemes=["bcrypt"]：bcrypt 是目前主流、安全的密碼雜湊演算法
# deprecated="auto"：舊雜湊值若遇到會自動標記為過期 (供未來升級用)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """把明文密碼轉成 bcrypt 雜湊，只在 register 時用。"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """比對明文密碼與 DB 裡的雜湊，登入時用。"""
    return pwd_context.verify(plain, hashed)


# ---------- JWT ----------
TokenType = Literal["access", "refresh"]


def create_token(
    user_id: UUID,
    token_type: TokenType,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    簽發一張 JWT。
    - sub：user_id (JWT 標準欄位，"subject")
    - type：access / refresh，解 token 時可辨別用途
    - exp：過期時間 (Unix timestamp)，jose 會自動驗證
    - iat：簽發時間
    """
    if expires_delta is None:
        if token_type == "access":
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        else:
            expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: TokenType) -> UUID:
    """
    驗證並解析 JWT，回傳 user_id。
    若過期、篡改、type 不符 → 拋 JWTError (由上層轉成 401)。
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as e:
        raise JWTError(f"Token 無效或已過期: {e}") from e

    if payload.get("type") != expected_type:
        raise JWTError(f"Token 類型不符，預期 {expected_type}")

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise JWTError("Token 缺少 sub 欄位")

    try:
        return UUID(user_id_str)
    except ValueError as e:
        raise JWTError(f"Token sub 不是有效的 UUID: {e}") from e
