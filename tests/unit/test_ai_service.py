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
