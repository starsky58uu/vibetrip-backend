"""公車 ETA 解析邏輯（含 status 順序）。"""

from app.services.transit_service import _parse_bus_eta


def test_none_raw_is_no_service() -> None:
    result = _parse_bus_eta(None, "207", "市政府")
    assert result.status == "no_service"
    assert result.eta_seconds is None


def test_departure_when_eta_within_30_seconds() -> None:
    result = _parse_bus_eta(
        {"StopStatus": 0, "EstimateTime": 25, "PlateNumb": "ABC-1234"},
        "207",
        "市政府",
    )
    assert result.status == "departure"
    assert result.eta_seconds == 25


def test_approaching_when_eta_between_31_and_60_seconds() -> None:
    result = _parse_bus_eta(
        {"StopStatus": 0, "EstimateTime": 45, "PlateNumb": "ABC-1234"},
        "207",
        "市政府",
    )
    assert result.status == "approaching"


def test_in_transit_when_eta_over_60_seconds() -> None:
    result = _parse_bus_eta(
        {"StopStatus": 0, "EstimateTime": 120, "PlateNumb": "ABC-1234"},
        "207",
        "市政府",
    )
    assert result.status == "in_transit"


def test_stop_status_no_service_clears_eta() -> None:
    result = _parse_bus_eta(
        {"StopStatus": 3, "EstimateTime": 30, "PlateNumb": "ABC-1234"},
        "207",
        "市政府",
    )
    assert result.status == "no_service"
    assert result.eta_seconds is None
