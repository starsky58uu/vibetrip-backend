"""系統端點 smoke tests。"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_root(client) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert "docs" in body


@pytest.mark.asyncio
async def test_healthz_ok_when_dependencies_up(client) -> None:
    with patch(
        "app.main.readiness",
        AsyncMock(return_value={"database": True, "redis": True}),
    ):
        response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["redis"] is True


@pytest.mark.asyncio
async def test_healthz_degraded_returns_503(client) -> None:
    with patch(
        "app.main.readiness",
        AsyncMock(return_value={"database": False, "redis": True}),
    ):
        response = await client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
