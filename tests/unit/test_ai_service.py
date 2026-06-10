"""AI 行程防幻覺驗證。"""

from app.services.ai_service import _validate_activities

NEARBY = [
    {"name": "路易莎咖啡", "rating": 4.5},
    {"name": "7-ELEVEN", "rating": 4.0},
    {"name": "大安森林公園", "rating": 4.8},
]


def test_keeps_valid_activity_names() -> None:
    items = [{"activity": "路易莎咖啡", "desc": "喝咖啡"}]
    out = _validate_activities(items, NEARBY)
    assert len(out) == 1
    assert out[0]["activity"] == "路易莎咖啡"


def test_replaces_hallucinated_place() -> None:
    items = [{"activity": "不存在的假店", "desc": "AI 編的"}]
    out = _validate_activities(items, NEARBY)
    assert len(out) == 1
    assert out[0]["activity"] in {p["name"] for p in NEARBY}


def test_partial_name_match() -> None:
    items = [{"activity": "路易莎", "desc": "縮寫"}]
    out = _validate_activities(items, NEARBY)
    assert out[0]["activity"] == "路易莎咖啡"


def test_empty_nearby_passthrough() -> None:
    items = [{"activity": "任意", "desc": "x"}]
    assert _validate_activities(items, []) == items


def test_duplicate_uses_next_highest_rated() -> None:
    items = [
        {"activity": "路易莎咖啡", "desc": "1"},
        {"activity": "路易莎咖啡", "desc": "2"},
    ]
    out = _validate_activities(items, NEARBY)
    names = [x["activity"] for x in out]
    assert len(names) == len(set(names))


def test_drops_station_when_candidates_exhausted() -> None:
    only = [{"name": "唯一店", "rating": 4.0}]
    items = [
        {"activity": "唯一店", "desc": "1"},
        {"activity": "唯一店", "desc": "2"},
        {"activity": "假店", "desc": "3"},
    ]
    out = _validate_activities(items, only)
    assert len(out) <= 2


def test_drops_duplicate_when_no_fallback_left() -> None:
    items = [
        {"activity": "路易莎咖啡", "desc": "第一站"},
        {"activity": "路易莎咖啡", "desc": "重複"},
        {"activity": "不存在的店", "desc": "第三站"},
    ]
    # 只有 3 個候選，第三站假店會替換；重複的第二站會換成別家
    out = _validate_activities(items, NEARBY)
    names = [x["activity"] for x in out]
    assert len(names) == len(set(names))
