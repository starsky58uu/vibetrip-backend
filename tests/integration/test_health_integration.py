"""整合環境健康檢查。"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_healthz_real_dependencies(integration_client: AsyncClient) -> None:
    resp = await integration_client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["redis"] is True
