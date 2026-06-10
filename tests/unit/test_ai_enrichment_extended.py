"""enrichment 剩餘分支。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai.enrichment import enrich_distances


@pytest.mark.asyncio
async def test_enrich_search_exception_and_no_routes() -> None:
    items = [{"activity": "X", "dist": ""}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.text_search = AsyncMock(side_effect=RuntimeError("fail"))
    mock_g.directions = AsyncMock(return_value={"routes": []})
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await enrich_distances(items, 25.0, 121.0, [])
    assert out[0]["dist"] == ""


@pytest.mark.asyncio
async def test_enrich_leg_exception_swallowed() -> None:
    items = [{"activity": "公園", "dist": ""}]
    nearby = [{"name": "公園", "lat": 25.0, "lon": 121.0}]
    mock_g = AsyncMock()
    mock_g.__aenter__ = AsyncMock(return_value=mock_g)
    mock_g.__aexit__ = AsyncMock(return_value=None)
    mock_g.directions = AsyncMock(side_effect=RuntimeError("leg fail"))
    with patch("app.services.external.google_client.GoogleMapsClient", return_value=mock_g):
        out = await enrich_distances(items, 25.0, 121.0, nearby)
    assert "dist" not in out[0] or out[0]["dist"] == ""
