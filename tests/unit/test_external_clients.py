"""外部 API client 測試（httpx mock）。"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.external.google_client import GoogleMapsClient, GoogleMapsError
from app.services.external.owm_client import OpenWeatherMapClient
from app.services.external.tdx_client import TDXClient


@pytest.mark.asyncio
async def test_google_nearby_search() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "OK", "results": [{"name": "Cafe"}]})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.aclose = AsyncMock()
    client = GoogleMapsClient()
    client._http = mock_http
    results = await client.nearby_search(25.0, 121.0, "cafe")
    assert results[0]["name"] == "Cafe"


@pytest.mark.asyncio
async def test_google_api_error_status() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "REQUEST_DENIED", "error_message": "denied"})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client = GoogleMapsClient()
    client._http = mock_http
    with pytest.raises(GoogleMapsError):
        await client.text_search("test")


@pytest.mark.asyncio
async def test_google_context_manager() -> None:
    async with GoogleMapsClient() as g:
        assert g is not None


@pytest.mark.asyncio
async def test_google_directions_with_departure() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "OK", "routes": []})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client = GoogleMapsClient()
    client._http = mock_http
    data = await client.directions(1.0, 2.0, 3.0, 4.0, mode="transit", departure_time=123)
    assert data["routes"] == []


@pytest.mark.asyncio
async def test_google_place_details() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "OK", "result": {"opening_hours": {}}})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client = GoogleMapsClient()
    client._http = mock_http
    result = await client.place_details("pid")
    assert "opening_hours" in result


@pytest.mark.asyncio
async def test_owm_current_weather() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"main": {"temp": 20}})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client = OpenWeatherMapClient()
    client._http = mock_http
    data = await client.current_weather(25.0, 121.0)
    assert data["main"]["temp"] == 20


@pytest.mark.asyncio
async def test_owm_forecast() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"list": []})
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client = OpenWeatherMapClient()
    client._http = mock_http
    data = await client.forecast_5day(25.0, 121.0)
    assert data["list"] == []


@pytest.mark.asyncio
async def test_owm_context_manager() -> None:
    async with OpenWeatherMapClient() as c:
        assert c is not None


@pytest.mark.asyncio
async def test_tdx_get_bus_eta_match() -> None:
    client = TDXClient()
    client._token = "tok"
    client._token_expires_at = time.time() + 3600
    client._http = AsyncMock()
    client._http.get = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=[{"StopName": {"Zh_tw": "市政府"}, "EstimateTime": 60}]),
        )
    )
    item = await client.get_bus_eta("Taipei", "207", "市政府")
    assert item["EstimateTime"] == 60


@pytest.mark.asyncio
async def test_tdx_get_bus_eta_no_match() -> None:
    client = TDXClient()
    client._token = "tok"
    client._token_expires_at = time.time() + 3600
    client._http = AsyncMock()
    client._http.get = AsyncMock(
        return_value=MagicMock(raise_for_status=MagicMock(), json=MagicMock(return_value=[]))
    )
    assert await client.get_bus_eta("Taipei", "207", "不存在") is None


@pytest.mark.asyncio
async def test_tdx_mrt_and_youbike() -> None:
    client = TDXClient()
    client._token = "tok"
    client._token_expires_at = time.time() + 3600
    client._http = AsyncMock()
    client._http.get = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=[{"StationID": "R10"}]),
        )
    )
    mrt = await client.get_mrt_eta("R10")
    assert mrt[0]["StationID"] == "R10"

    client._http.get = AsyncMock(
        return_value=MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=[{"StationID": "500101001"}]),
        )
    )
    bikes = await client.get_youbike_stations_status()
    assert bikes[0]["StationID"] == "500101001"


@pytest.mark.asyncio
async def test_tdx_token_from_redis_cache() -> None:
    client = TDXClient()
    client._http = AsyncMock()
    with patch(
        "app.services.external.tdx_client.cache_get_json",
        AsyncMock(return_value={"access_token": "cached", "expires_at": time.time() + 3600}),
    ):
        token = await client._get_access_token()
    assert token == "cached"


@pytest.mark.asyncio
async def test_tdx_token_fetches_new() -> None:
    client = TDXClient()
    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    post_resp.json = MagicMock(return_value={"access_token": "newtok", "expires_in": 3600})
    client._http = AsyncMock()
    client._http.post = AsyncMock(return_value=post_resp)
    with (
        patch("app.services.external.tdx_client.cache_get_json", AsyncMock(return_value=None)),
        patch("app.services.external.tdx_client.cache_set_json", AsyncMock()),
        patch("app.services.external.tdx_client.get_redis", AsyncMock()),
    ):
        token = await client._get_access_token()
    assert token == "newtok"


@pytest.mark.asyncio
async def test_tdx_context_manager() -> None:
    async with TDXClient() as tdx:
        assert tdx is not None
