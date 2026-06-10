"""Trip template 整合測試 — GET /trips/{id} 僅適用 DB seed。"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trip import TripTemplate

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_seeded_trip_template(
    db_session: AsyncSession, integration_client: AsyncClient
) -> None:
    result = await db_session.execute(select(TripTemplate).limit(1))
    template = result.scalar_one_or_none()
    assert template is not None, "init_db 應已 seed trip_templates"

    resp = await integration_client.get(f"/api/v1/trips/{template.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(template.id)
    assert body["title"] == template.title


@pytest.mark.asyncio
async def test_get_unknown_trip_returns_404(integration_client: AsyncClient) -> None:
    resp = await integration_client.get("/api/v1/trips/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404
