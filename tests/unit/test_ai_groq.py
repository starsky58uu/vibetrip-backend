"""Groq 文案生成測試。"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.ai.groq import call_groq, slot_time_hint


def test_slot_time_hint_five_lines() -> None:
    now = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    lines = slot_time_hint(now).splitlines()
    assert len(lines) == 5
    assert "第1站" in lines[0]


@pytest.mark.asyncio
async def test_call_groq_with_nearby_afternoon() -> None:
    nearby = [
        {"name": "咖啡", "rating": 4.5, "address": "addr", "closes_at": "22:00"},
        {"name": "24h", "rating": 4.0, "address": "addr2", "closes_at": "24:00"},
    ]
    payload = {"title": "午後", "subtitle": "s", "items": []}
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    with patch("app.services.ai.groq.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch("app.services.ai.groq.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = await call_groq("cafe", 25.0, 121.0, "Clear", nearby)
    assert result["title"] == "午後"


@pytest.mark.asyncio
async def test_call_groq_late_night_no_nearby() -> None:
    payload = {"title": "深夜", "items": []}
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    with patch("app.services.ai.groq.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch("app.services.ai.groq.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 10, 23, 0, tzinfo=ZoneInfo("Asia/Taipei"))
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            result = await call_groq("food", 25.0, 121.0, None, [])
    assert result["title"] == "深夜"


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", [4, 7, 23])
async def test_call_groq_time_branches(hour: int) -> None:
    payload = {"title": "x", "items": []}
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    with patch("app.services.ai.groq.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        with patch("app.services.ai.groq.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 6, 10, hour, 0, tzinfo=ZoneInfo("Asia/Taipei")
            )
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await call_groq("walk", 25.0, 121.0, None, [])
