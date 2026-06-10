"""Cursor-based 分頁編解碼。"""

import base64
import json
from typing import Any

from fastapi import HTTPException, status


def encode_cursor(data: dict[str, Any]) -> str:
    raw = json.dumps(data, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cursor 格式無效",
        ) from e
