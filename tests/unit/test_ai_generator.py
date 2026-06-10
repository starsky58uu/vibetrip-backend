"""AI generator 主流程測試。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.generator import generate_trip


@pytest.mark.asyncio
async def test_generate_trip_cache_hit() -> None:
    cached = {"title": "快取行程", "items": []}
    mock_redis = AsyncMock()
    with (
        patch("app.services.ai.generator.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.services.ai.generator.cache_get_json", AsyncMock(return_value=cached)),
    ):
        result = await generate_trip("cafe", 25.0, 121.0, "Clear")
    assert result["title"] == "快取行程"


@pytest.mark.asyncio
async def test_generate_trip_full_pipeline(monkeypatch) -> None:
    nearby = [{"name": "A", "rating": 4.5, "lat": 25.0, "lon": 121.0}]
    groq_result = {"title": "T", "subtitle": "S", "items": [{"activity": "A", "dur": "45min"}]}
    mock_redis = AsyncMock()
    with (
        patch("app.services.ai.generator.get_redis", AsyncMock(return_value=mock_redis)),
        patch("app.services.ai.generator.cache_get_json", AsyncMock(return_value=None)),
        patch("app.services.ai.generator.cache_set_json", AsyncMock()),
        patch("app.services.ai.generator.search_nearby", AsyncMock(return_value=nearby)),
        patch("app.services.ai.generator.fetch_closing_times", AsyncMock()),
        patch("app.services.ai.generator.filter_closing_soon", return_value=nearby),
        patch("app.services.ai.generator.call_groq", AsyncMock(return_value=groq_result)),
        patch("app.services.ai.generator.validate_activities", side_effect=lambda items, _n: items),
        patch(
            "app.services.ai.generator.validate_closing_times", side_effect=lambda items, _n: items
        ),
        patch(
            "app.services.ai.generator.enrich_distances",
            AsyncMock(side_effect=lambda items, *_a: items),
        ),
        patch("app.services.ai.generator.datetime") as mock_dt,
    ):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        mock_dt.now.return_value = datetime(2026, 6, 10, 14, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        result = await generate_trip("cafe", 25.0, 121.0, "Clear")
    assert result["title"] == "T"


@pytest.mark.asyncio
async def test_generate_trip_enrichment_failure_swallowed() -> None:
    nearby = [{"name": "A", "rating": 4.0}]
    groq_result = {"title": "T", "items": [{"activity": "A"}]}
    with (
        patch("app.services.ai.generator.get_redis", AsyncMock(return_value=AsyncMock())),
        patch("app.services.ai.generator.cache_get_json", AsyncMock(return_value=None)),
        patch("app.services.ai.generator.cache_set_json", AsyncMock()),
        patch("app.services.ai.generator.search_nearby", AsyncMock(return_value=nearby)),
        patch("app.services.ai.generator.call_groq", AsyncMock(return_value=groq_result)),
        patch("app.services.ai.generator.validate_activities", side_effect=lambda items, _n: items),
        patch(
            "app.services.ai.generator.enrich_distances",
            AsyncMock(side_effect=RuntimeError("fail")),
        ),
        patch("app.services.ai.generator.datetime") as mock_dt,
    ):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        mock_dt.now.return_value = datetime(2026, 6, 10, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        result = await generate_trip("walk", 25.0, 121.0, None, exclude_trip_ids=[])
    assert result["title"] == "T"
