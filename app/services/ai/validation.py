"""AI 輸出防幻覺驗證。"""

import logging

logger = logging.getLogger(__name__)


def validate_activities(items: list[dict], nearby: list[dict]) -> list[dict]:
    """
    確保 AI 回傳的每個 activity 名稱確實存在於 nearby 清單中、
    且每個地點在同一份行程內不重複出現。
    觸發替換的情況：
      1. AI 編造不在清單的地點
      2. AI 把同一家真實店名連續排了好幾站（會把第 2 次以後改成別家）
    替換邏輯：優先選「尚未使用」的最高評分地點；
    所有地點都已使用過時，依「使用次數最少 → 評分最高」排序取替補。
    """
    if not nearby:
        return items

    def find_real_name(activity: str) -> str | None:
        # 1. 完全相符
        for p in nearby:
            if p["name"] == activity:
                return p["name"]
        # 2. 部分包含（AI 可能縮寫或加括號）
        for p in nearby:
            if p["name"] in activity or activity in p["name"]:
                return p["name"]
        return None

    validated = []
    # 統計每個地點已被用幾次，用來決定備選順序
    use_count: dict[str, int] = {p["name"]: 0 for p in nearby}

    for item in items:
        real = find_real_name(item.get("activity", ""))
        used_names = {v["activity"] for v in validated}

        # 真名存在「且」尚未在本趟用過 → 直接收下
        if real and real not in used_names:
            use_count[real] = use_count.get(real, 0) + 1
            validated.append({**item, "activity": real})
            continue

        # 否則：AI 編造不在清單、或重複選同一家 → 換成未使用的最高評分地點
        by_rating = sorted(nearby, key=lambda x: -x.get("rating", 0))
        fallback_place = next(
            (p for p in by_rating if p["name"] not in used_names),
            None,
        )
        if fallback_place is None:
            # nearby 已全數用過（候選清單比行程站數少）→ 寧可少一站也不重複
            logger.info("候選清單已用完，移除站點 '%s'", item.get("activity"))
            continue

        use_count[fallback_place["name"]] = use_count.get(fallback_place["name"], 0) + 1
        reason = "已重複" if real else "不在清單"
        logger.info(
            "替換站點 '%s' (%s) → '%s'",
            item.get("activity"),
            reason,
            fallback_place["name"],
        )
        validated.append({**item, "activity": fallback_place["name"]})

    return validated
