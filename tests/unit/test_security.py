"""JWT 與密碼雜湊單元測試。"""

from datetime import timedelta
from uuid import uuid4

import pytest
from jose import JWTError

from app.core.security import (
    create_token,
    decode_token,
    decode_token_jti,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password() -> None:
    hashed = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    assert decode_token(token, expected_type="access") == user_id


def test_refresh_token_rejects_access_type() -> None:
    user_id = uuid4()
    access = create_token(user_id, token_type="access")
    with pytest.raises(JWTError, match="類型不符"):
        decode_token(access, expected_type="refresh")


def test_verify_password_corrupt_hash_returns_false() -> None:
    assert verify_password("x", "not-a-valid-bcrypt-hash") is False


def test_decode_token_jti_refresh() -> None:
    user_id = uuid4()
    jti = str(uuid4())
    token = create_token(user_id, token_type="refresh", jti=jti)
    decoded_id, decoded_jti = decode_token_jti(token, expected_type="refresh")
    assert decoded_id == user_id
    assert decoded_jti == jti


def test_decode_token_jti_missing_jti() -> None:
    from jose import jwt

    from app.core.config import settings

    payload = {"sub": str(uuid4()), "type": "access", "exp": 9999999999}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(JWTError, match="jti"):
        decode_token_jti(token, expected_type="access")


def test_decode_token_jti_invalid_uuid() -> None:
    from jose import jwt

    from app.core.config import settings

    payload = {"sub": "not-uuid", "type": "access", "jti": "x", "exp": 9999999999}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(JWTError, match="UUID"):
        decode_token_jti(token, expected_type="access")


def test_create_token_custom_expiry() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access", expires_delta=timedelta(minutes=5))
    assert decode_token(token, expected_type="access") == user_id


def test_tampered_token_raises() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    header, payload, _sig = token.split(".")
    bad = f"{header}.{payload}.invalidsignature"
    with pytest.raises(JWTError):
        decode_token(bad, expected_type="access")
