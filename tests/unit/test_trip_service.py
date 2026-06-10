"""盲盒 vibe 解析邏輯。"""

import random

from app.schemas.trip import RecommendRequest
from app.services.trip_service import _resolve_vibe


def _req(**kwargs) -> RecommendRequest:
    base = {"latitude": 25.033, "longitude": 121.565}
    base.update(kwargs)
    return RecommendRequest(**base)


def test_rainy_walk_becomes_rain() -> None:
    assert _resolve_vibe(_req(vibe_key="walk", weather_condition="Rain")) == "rain"


def test_rainy_photo_becomes_rain() -> None:
    assert _resolve_vibe(_req(vibe_key="photo", weather_condition="drizzle")) == "rain"


def test_clear_weather_keeps_walk() -> None:
    assert _resolve_vibe(_req(vibe_key="walk", weather_condition="Clear")) == "walk"


def test_random_picks_from_pool(monkeypatch) -> None:
    monkeypatch.setattr(random, "choice", lambda options: options[0])
    assert _resolve_vibe(_req(vibe_key="random")) == "cafe"
