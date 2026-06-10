"""Spots / Uploads 端點測試。"""

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.spot import (
    CommunitySpotResponse,
    PaginatedCommunitySpotsResponse,
    PersonalSpotResponse,
    SpotAuthor,
    ToggleLikeResponse,
    ToggleSaveResponse,
    ViewerState,
)


def _personal_response() -> PersonalSpotResponse:
    return PersonalSpotResponse(
        id=uuid4(),
        owner_id=uuid4(),
        latitude=25.033,
        longitude=121.565,
        note="note",
        image_url=None,
        is_public=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_spots_personal_crud(authed_client) -> None:
    spot = _personal_response()
    with (
        patch(
            "app.api.v1.endpoints.spots.spot_service.create_personal_spot",
            AsyncMock(return_value=spot),
        ),
        patch(
            "app.api.v1.endpoints.spots.spot_service.list_personal_spots",
            AsyncMock(return_value=[spot]),
        ),
        patch(
            "app.api.v1.endpoints.spots.spot_service.update_personal_spot",
            AsyncMock(return_value=spot),
        ),
        patch("app.api.v1.endpoints.spots.spot_service.delete_personal_spot", AsyncMock()),
    ):
        create = await authed_client.post(
            "/api/v1/spots/personal",
            json={"latitude": 25.033, "longitude": 121.565, "note": "n"},
        )
        listing = await authed_client.get("/api/v1/spots/personal")
        update = await authed_client.patch(
            f"/api/v1/spots/personal/{spot.id}",
            json={"note": "new"},
        )
        delete = await authed_client.delete(f"/api/v1/spots/personal/{spot.id}")
    assert create.status_code == 201
    assert listing.status_code == 200
    assert update.status_code == 200
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_spots_community_and_interactions(client, authed_client) -> None:
    community = CommunitySpotResponse(
        id=uuid4(),
        author=SpotAuthor(id=uuid4(), username="a", display_name="A", avatar_url=None),
        latitude=25.0,
        longitude=121.0,
        content="c",
        image_url=None,
        likes_count=1,
        saves_count=0,
        created_at=datetime.now(UTC),
        viewer_state=ViewerState(),
    )
    page = PaginatedCommunitySpotsResponse(
        data=[community], pagination={"next_cursor": None, "has_more": False}
    )
    with (
        patch(
            "app.api.v1.endpoints.spots.spot_service.list_community_spots",
            AsyncMock(return_value=page),
        ),
        patch(
            "app.api.v1.endpoints.spots.spot_service.list_saved_spots",
            AsyncMock(return_value=[community]),
        ),
        patch(
            "app.api.v1.endpoints.spots.spot_service.toggle_like",
            AsyncMock(return_value=ToggleLikeResponse(is_liked=True, likes_count=2)),
        ),
        patch(
            "app.api.v1.endpoints.spots.spot_service.toggle_save",
            AsyncMock(return_value=ToggleSaveResponse(is_saved=True, saves_count=1)),
        ),
    ):
        r1 = await client.get("/api/v1/spots/community")
        r2 = await authed_client.get("/api/v1/spots/saved")
        r3 = await authed_client.post(f"/api/v1/spots/community/{community.id}/like")
        r4 = await authed_client.post(f"/api/v1/spots/community/{community.id}/save")
    assert r1.status_code == r2.status_code == r3.status_code == r4.status_code == 200


@pytest.mark.asyncio
async def test_upload_image_success(authed_client, tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PUBLIC_CDN_BASE", "http://cdn.example/uploads")
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    with patch("app.api.v1.endpoints.uploads.rate_limit_upload_image", AsyncMock()):
        files = {"file": ("test.jpg", BytesIO(b"fake-image"), "image/jpeg")}
        resp = await authed_client.post("/api/v1/uploads/image", files=files)
    assert resp.status_code == 200
    assert "image_url" in resp.json()


@pytest.mark.asyncio
async def test_upload_image_bad_mime(authed_client) -> None:
    with patch("app.api.v1.endpoints.uploads.rate_limit_upload_image", AsyncMock()):
        files = {"file": ("x.txt", BytesIO(b"text"), "text/plain")}
        resp = await authed_client.post("/api/v1/uploads/image", files=files)
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_image_too_large(authed_client, tmp_path) -> None:
    with (
        patch("app.api.v1.endpoints.uploads.rate_limit_upload_image", AsyncMock()),
        patch("app.api.v1.endpoints.uploads.settings.UPLOAD_DIR", str(tmp_path)),
        patch("app.api.v1.endpoints.uploads._MAX_BYTES", 512),
    ):
        files = {"file": ("big.jpg", BytesIO(b"x" * 1024), "image/jpeg")}
        resp = await authed_client.post("/api/v1/uploads/image", files=files)
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_image_localhost_base_from_request(
    authed_client, tmp_path, monkeypatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "PUBLIC_CDN_BASE", "http://localhost:8000/static/uploads")
    with patch("app.api.v1.endpoints.uploads.rate_limit_upload_image", AsyncMock()):
        files = {"file": ("a.png", BytesIO(b"png"), "image/png")}
        resp = await authed_client.post("/api/v1/uploads/image", files=files)
    assert "http://test/static/uploads" in resp.json()["image_url"]


@pytest.mark.asyncio
async def test_upload_image_write_failure(authed_client, tmp_path) -> None:
    with (
        patch("app.api.v1.endpoints.uploads.rate_limit_upload_image", AsyncMock()),
        patch("app.api.v1.endpoints.uploads.settings.UPLOAD_DIR", str(tmp_path)),
        patch("builtins.open", side_effect=OSError("disk full")),
    ):
        files = {"file": ("a.jpg", BytesIO(b"x"), "image/jpeg")}
        resp = await authed_client.post("/api/v1/uploads/image", files=files)
    assert resp.status_code == 500
