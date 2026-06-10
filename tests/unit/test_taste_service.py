"""口味分析服務測試。"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.taste_service import (
    _classify_hour,
    _generate_with_groq,
    _sparse_profile,
    get_taste_profile,
)


def test_sparse_profile() -> None:
    p = _sparse_profile(1)
    assert p["generated"] is False
    assert p["spots_count"] == 1
    assert "再記錄" in p["subtitle"]


@pytest.mark.parametrize(
    ("hour", "label"),
    [
        (7, "清晨"),
        (11, "上午"),
        (14, "下午"),
        (19, "傍晚"),
        (22, "夜晚"),
        (2, "深夜"),
    ],
)
def test_classify_hour(hour: int, label: str) -> None:
    assert label in _classify_hour(hour)


@pytest.mark.asyncio
async def test_get_taste_profile_cache_hit() -> None:
    user_id = uuid4()
    cached = {
        "generated": True,
        "spots_count": 5,
        "headline": "h",
        "subtitle": "s",
        "tags": [],
        "top_vibes": [],
        "roaming_style": "x",
    }
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached))
    db = AsyncMock()
    with patch("app.services.taste_service.get_redis", AsyncMock(return_value=mock_redis)):
        result = await get_taste_profile(db, user_id, refresh=False)
    assert result["headline"] == "h"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_taste_profile_sparse() -> None:
    user_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    spot = MagicMock()
    spot.created_at = datetime(2026, 1, 1, 14, 0)
    spot.note = "note"
    spot.image_url = None
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[spot, spot])))
        )
    )
    with patch("app.services.taste_service.get_redis", AsyncMock(return_value=mock_redis)):
        result = await get_taste_profile(db, user_id, refresh=True)
    assert result["generated"] is False


@pytest.mark.asyncio
async def test_generate_with_groq_parses_json() -> None:
    spots = []
    for i in range(3):
        s = MagicMock()
        s.created_at = datetime(2026, 1, 1, 10 + i, 0)
        s.note = f"note{i}"
        s.image_url = "http://img" if i == 0 else None
        spots.append(s)

    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "headline": "你是夜貓",
                        "subtitle": "愛深夜出沒",
                        "tags": ["夜行"],
                        "roaming_style": "深夜型",
                        "top_vibes": ["Café Drift"],
                    }
                )
            )
        )
    ]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    with patch("app.services.taste_service.AsyncGroq", return_value=mock_client):
        result = await _generate_with_groq(spots)
    assert result["generated"] is True
    assert result["spots_count"] == 3


@pytest.mark.asyncio
async def test_generate_with_groq_json_decode_fallback() -> None:
    spots = [
        MagicMock(created_at=datetime(2026, 1, 1, 12), note="a", image_url=None) for _ in range(3)
    ]
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    'prefix {"headline":"x","subtitle":"y","tags":[],'
                    '"roaming_style":"z","top_vibes":[]} suffix'
                )
            )
        )
    ]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    with patch("app.services.taste_service.AsyncGroq", return_value=mock_client):
        result = await _generate_with_groq(spots)
    assert result["generated"] is True


@pytest.mark.asyncio
async def test_generate_with_groq_empty_fallback() -> None:
    spots = [
        MagicMock(created_at=datetime(2026, 1, 1, 12), note="", image_url=None) for _ in range(3)
    ]
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="not json"))]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
    with patch("app.services.taste_service.AsyncGroq", return_value=mock_client):
        result = await _generate_with_groq(spots)
    assert result["generated"] is True
    assert result["tags"] == []
