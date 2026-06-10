"""Cursor 分頁編解碼。"""

import pytest
from fastapi import HTTPException

from app.core.pagination import decode_cursor, encode_cursor


def test_cursor_round_trip() -> None:
    data = {"created_at": "2026-01-01T00:00:00+00:00", "id": "abc-123"}
    token = encode_cursor(data)
    assert decode_cursor(token) == data


def test_invalid_cursor_raises_400() -> None:
    with pytest.raises(HTTPException) as exc:
        decode_cursor("not-a-valid-cursor")
    assert exc.value.status_code == 400
