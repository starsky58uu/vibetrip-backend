"""JWT 與密碼雜湊單元測試。"""

from uuid import uuid4

import pytest
from jose import JWTError

from app.core.security import (
    create_token,
    decode_token,
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


def test_tampered_token_raises() -> None:
    user_id = uuid4()
    token = create_token(user_id, token_type="access")
    bad = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(JWTError):
        decode_token(bad, expected_type="access")
