"""Users 端點測試。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_get_me(authed_client, mock_user) -> None:
    mock_user.username = "meuser"
    mock_user.email = "me@example.com"
    mock_user.display_name = "Me"
    mock_user.avatar_url = None
    mock_user.created_at = datetime.now(UTC)
    resp = await authed_client.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "meuser"


@pytest.mark.asyncio
async def test_get_me_stats_naive_created_at(authed_client, mock_user, mock_db) -> None:
    mock_user.created_at = datetime(2025, 1, 1)
    mock_db.scalar = AsyncMock(side_effect=[0, 0])
    resp = await authed_client.get("/api/v1/users/me/stats")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_me_stats(authed_client, mock_user, mock_db) -> None:
    mock_user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    mock_db.scalar = AsyncMock(side_effect=[5, 2])
    resp = await authed_client.get("/api/v1/users/me/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["spots_count"] == 5
    assert body["saved_count"] == 2
    assert body["days"] >= 0


@pytest.mark.asyncio
async def test_update_me(authed_client, mock_user, mock_db) -> None:
    mock_user.created_at = datetime.now(UTC)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    resp = await authed_client.patch(
        "/api/v1/users/me",
        json={"display_name": "New Name", "avatar_url": "http://img"},
    )
    assert resp.status_code == 200
    assert mock_user.display_name == "New Name"
