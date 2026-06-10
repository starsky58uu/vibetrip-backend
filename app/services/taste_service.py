"""
AI 口味分析服務 — 解讀使用者的城市漫遊個性。

流程：
1. 讀使用者 personal_spots（最多 50 筆）
2. 統計時段分布、備注關鍵詞、拍照習慣
3. 不滿 3 筆 → 回傳引導文案，不浪費 Groq 額度
4. 滿 3 筆以上 → 呼叫 Groq LLaMA 3.3，生成結構化 JSON
5. 結果寫入 Redis，TTL 12 小時
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import UUID

from groq import AsyncGroq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import build_key, cache_get_json, cache_set_json, get_redis
from app.db.models.spot import PersonalSpot

logger = logging.getLogger(__name__)

_CACHE_TTL = 12 * 3600  # 12 小時
_MIN_SPOTS = 3  # 至少要幾筆足跡才分析
_VIBE_OPTIONS = [
    "Café Drift",
    "Hungry Mood",
    "Photo Hunt",
    "Rain Shelter",
    "Slow Walk",
    "Tiny Gift",
    "Surprise Me",
]


# ── Public API ────────────────────────────────────────────────────────────────


async def get_taste_profile(
    db: AsyncSession,
    user_id: UUID,
    refresh: bool = False,
) -> dict:
    """
    取得使用者 AI 口味分析。
    refresh=True 時強制重新呼叫 Groq，否則優先讀快取。
    """
    cache_key = build_key("taste", "profile", user_id)

    if not refresh:
        redis = await get_redis()
        cached = await cache_get_json(redis, cache_key)
        if cached is not None:
            return cached

    # 讀足跡
    result_proxy = await db.execute(
        select(PersonalSpot)
        .where(PersonalSpot.owner_id == user_id)
        .order_by(PersonalSpot.created_at.desc())
        .limit(50)
    )
    spots = result_proxy.scalars().all()

    if len(spots) < _MIN_SPOTS:
        profile = _sparse_profile(len(spots))
    else:
        profile = await _generate_with_groq(spots)

    redis = await get_redis()
    await cache_set_json(redis, cache_key, profile, ttl_seconds=_CACHE_TTL)

    return profile


# ── 私有 helpers ──────────────────────────────────────────────────────────────


def _sparse_profile(count: int) -> dict:
    """足跡太少時回傳引導文案，不呼叫 AI。"""
    remain = _MIN_SPOTS - count
    return {
        "generated": False,
        "spots_count": count,
        "headline": "你的漫遊故事才剛開始",
        "subtitle": f"再記錄 {remain} 個足跡，AI 就能解讀你的城市口味",
        "tags": ["城市探索者"],
        "roaming_style": "初探型",
        "top_vibes": [],
    }


def _classify_hour(h: int) -> str:
    if 6 <= h < 10:
        return "清晨(06-10)"
    if 10 <= h < 12:
        return "上午(10-12)"
    if 12 <= h < 18:
        return "下午(12-18)"
    if 18 <= h < 20:
        return "傍晚(18-20)"
    if 20 <= h < 24:
        return "夜晚(20-00)"
    return "深夜(00-06)"


async def _generate_with_groq(spots: list[PersonalSpot]) -> dict:
    """分析足跡資料，呼叫 Groq，回傳結構化口味報告。"""
    # ── 資料統計 ────────────────────────────────────────────────────────────
    hour_buckets: dict[str, int] = {}
    notes: list[str] = []
    has_photos = 0

    for spot in spots:
        ts = spot.created_at
        h = ts.hour if isinstance(ts, datetime) else 14
        slot = _classify_hour(h)
        hour_buckets[slot] = hour_buckets.get(slot, 0) + 1

        note = (spot.note or "").strip()
        if note and note not in ("足跡",):
            notes.append(note[:80])

        if spot.image_url:
            has_photos += 1

    # 排序取最多的時段
    sorted_slots = sorted(hour_buckets, key=hour_buckets.get, reverse=True)
    top_time = sorted_slots[0] if sorted_slots else "下午(12-18)"
    sec_time = sorted_slots[1] if len(sorted_slots) > 1 else top_time

    notes_block = "\n".join(f"- {n}" for n in notes[:15]) if notes else "（用戶沒有留下文字備注）"
    hour_summary = "、".join(
        f"{k}×{v}" for k, v in sorted(hour_buckets.items(), key=lambda x: -x[1])
    )
    vibes_str = " / ".join(_VIBE_OPTIONS)

    prompt = f"""\
你是一位擅長解讀都市旅人個性的文字工作者。
根據以下城市漫遊足跡資料，生成一份簡短、有文學感的「口味分析報告」。

== 足跡統計 ==
- 總足跡數：{len(spots)} 個
- 附有照片：{has_photos} 個（說明拍照頻率）
- 最常出門時段：{top_time}（次多：{sec_time}）
- 時段詳細分布：{hour_summary}

== 備注文字樣本（用戶自己寫的） ==
{notes_block}

== 輸出規則 ==
請直接回傳合法 JSON，不要有任何說明或 markdown 包裝：
{{
  "headline": "一句15字以內的核心口味描述，用「你是」或「你像」開頭，要有畫面感",
  "subtitle": "一句20字以內的補充，說明他的漫遊習慣或時間偏好",
  "tags": ["標籤1","標籤2","標籤3"],
  "roaming_style": "4-6字的漫遊人格，例如：深夜探險家、午後療癒型",
  "top_vibes": ["Vibe1","Vibe2"]
}}

注意事項：
- tags 2–4 個，每個 2–5 字
- top_vibes 選 1–2 個，只能從這裡選：{vibes_str}
- 語調要像詩、有溫度，不要太商業或太口語
- 絕對不要捏造具體地點或店家名稱
- 若備注很少，從時段與頻率推斷個性
"""

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    resp = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.88,
        max_tokens=300,
        response_format={"type": "json_object"},
    )

    raw = resp.choices[0].message.content.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # 防呆：Groq 偶爾會在 JSON 前後加多餘文字
        import re

        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group(0)) if m else {}

    # 補充元資料
    result["generated"] = True
    result["spots_count"] = len(spots)

    # 確保 tags / top_vibes 是陣列
    if not isinstance(result.get("tags"), list):
        result["tags"] = []
    if not isinstance(result.get("top_vibes"), list):
        result["top_vibes"] = []

    logger.info(
        "口味分析完成: %s (%d spots)",
        result.get("roaming_style", "?"),
        len(spots),
    )
    return result
