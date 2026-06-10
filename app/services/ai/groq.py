"""Groq LLM 行程文案生成。"""

import json
import logging
from datetime import datetime

from groq import AsyncGroq

from app.core.config import settings
from app.services.ai.constants import TW_TZ, VIBE_COMPOSITION_RULE, VIBE_ZH

logger = logging.getLogger(__name__)
client = AsyncGroq(api_key=settings.GROQ_API_KEY)


def slot_time_hint(now_tw: datetime) -> str:
    """
    計算行程各站的預估到達時刻字串，餵給 AI 做打烊檢查參考。
    假設第一站 10 分鐘後到，每站停留 45 分鐘 + 10 分鐘移動。
    """
    cursor = now_tw.hour * 60 + now_tw.minute + 10
    lines = []
    for i in range(5):
        hh = (cursor // 60) % 24
        mm = cursor % 60
        lines.append(f"  第{i + 1}站：約 {hh:02d}:{mm:02d}")
        cursor += 45 + 10
    return "\n".join(lines)


async def call_groq(
    vibe_key: str, lat: float, lon: float, weather: str | None, nearby: list[dict]
) -> dict:
    vibe_zh = VIBE_ZH.get(vibe_key, vibe_key)
    weather_hint = f"，今天天氣是{weather}" if weather else ""
    now_tw = datetime.now(TW_TZ)
    current_time = now_tw.strftime("%H:%M")
    hour = now_tw.hour

    # ── 時段限制（細分深夜 / 凌晨 / 清晨）──────────────────────────────────────
    if hour >= 22 or hour < 3:
        # 深夜 22:00～02:59
        time_constraint = (
            "\n【深夜行程規則 ⚠️】現在是深夜，行程只需 2～3 個地點。"
            "主力推薦：居酒屋、餐酒館、酒吧、漫畫咖啡廳（24小時）、"
            "宵夜小吃（鹹酥雞攤、深夜拉麵、牛肉麵湯）、KTV、夜間景觀台、夜間開放公園。"
            "嚴禁：以麥當勞或速食店當主要地點（便利商店只能是「順路買杯咖啡」的過渡點）；"
            "嚴禁推薦夕陽、日落、日出相關活動；嚴禁推薦一般日間咖啡廳或商店。"
            "最後一個地點要能讓人待到凌晨（酒吧、居酒屋、漫畫咖啡廳均可）。"
        )
    elif hour < 6:
        # 凌晨 03:00～05:59
        time_constraint = (
            "\n【凌晨行程規則 ⚠️】現在是凌晨，行程只需 2～3 個地點，節奏輕鬆。"
            "適合推薦：傳統批發市場（部分 04:00 起開始進貨）、"
            "24 小時便利商店（買消夜、補充能量）、"
            "夜間開放公園或河濱步道（吹風看星星）、凌晨仍有宵夜攤的地點、夜間景觀台。"
            "嚴禁推薦夕陽、日落、一般日間才開的商家。"
        )
    elif hour < 9:
        # 清晨 06:00～08:59
        time_constraint = (
            "\n【清晨行程規則 ⚠️】現在是清晨，行程 2～3 個地點，節奏輕鬆不要塞太滿。"
            "適合推薦：傳統早市、晨間公園（太極/慢跑/散步）、早餐店、早開咖啡廳、河濱晨騎路線。"
            "便利商店可以是買早餐的選項之一，但不能是行程唯一亮點。"
            "嚴禁推薦需要等到中午才開的店家或夜間才有的活動。"
        )
    else:
        time_constraint = ""

    # ── 每種 vibe 的人性化行程組成規則 ──────────────────────────────────────────
    composition_rule = VIBE_COMPOSITION_RULE.get(vibe_key, "")

    if nearby:

        def _fmt_place(i: int, p: dict) -> str:
            ca = p.get("closes_at", "")
            if ca == "24:00":
                close_tag = "，24小時"
            elif ca:
                # "21:30" → 打烊 21:30；"01:00↑" → 打烊 01:00(次日)
                close_tag = f"，打烊 {ca.replace('↑', '(次日)')}"
            else:
                close_tag = ""
            return f"{i + 1}. {p['name']}（評分 {p['rating']}{close_tag}）— {p['address']}"

        place_list = "\n".join(_fmt_place(i, p) for i, p in enumerate(nearby))
        places_block = f"""
【附近真實店家清單（來自 Google Maps，1.5km 以內）】
{place_list}

⚠️ 絕對規則（違反即為錯誤輸出）：
- activity 欄位必須逐字使用上方清單中的完整店名，一個字都不能改
- 嚴禁自行創造、捏造、縮寫或翻譯任何店名
- 每個地點在行程中只能出現 1 次（不要重複同一個地名）
- 若清單地點數量不足以安排 3～4 個不同地點，寧可縮短行程（只排 2 個地點），也不要重複同一個地點
- 「散步消化」「休息一下」「買杯飲料」等過渡活動，activity 欄位也必須選清單中一個真實地點（例如選公園名或飲料店名），用 desc 說明你要做什麼
- 有「打烊」時間的地點，必須確認：該地點的到達時間（前面所有 dur 累加）＋ 本站 dur ≤ 打烊時間，否則不要安排或提前排入行程
- 快打烊的地點（剩餘時間少）要優先排在行程前面
"""
    else:
        # nearby 完全空（例如：深夜找不到任何開著的店）
        if hour >= 22 or hour < 3:
            places_block = (
                "現在是深夜，附近商家幾乎都已打烊。"
                "請推薦此時段確實開放、人可以去的地方（只需 2～3 個地點），例如：\n"
                "・居酒屋、餐酒館、酒吧（深夜的靈魂地點）\n"
                "・漫畫咖啡廳（24小時，可以待到天亮）\n"
                "・鹹酥雞攤、深夜拉麵、牛肉麵湯等宵夜小吃\n"
                "・KTV、夜間景觀台\n"
                "・夜間開放公園或河濱步道（作為散步過渡）\n"
                "嚴禁以麥當勞作為主要地點。請選使用者座標附近真實存在的地點，不要捏造店名。"
            )
        elif hour < 6:
            places_block = (
                "現在是凌晨，大多數商家都已打烊。只需 2～3 個地點，例如：\n"
                "・24 小時便利商店（買消夜、補充能量）\n"
                "・夜間開放公園或河濱步道（吹風看星星）\n"
                "・傳統批發市場（部分清晨 04:00 起開始進貨，可去感受氣氛）\n"
                "請選使用者座標附近真實存在的地點，不要捏造店名。"
            )
        elif hour < 9:
            places_block = (
                "現在是清晨，請推薦清晨開放的場所，"
                "例如：早餐店、晨間公園、傳統市場、早開咖啡廳等。"
                "請選使用者座標附近真實存在的地點。"
            )
        else:
            places_block = "請推薦使用者附近真實存在、Google 評分 3.5 以上的台灣在地店家。"

    prompt = f"""你是台灣在地旅遊達人，深知台灣人的生活節奏與真實喜好。
請為一位想要「{vibe_zh}」體驗的旅客，
在台灣（使用者目前座標：緯度 {lat:.4f}，經度 {lon:.4f}）{weather_hint}，
規劃一份人性化的步行行程。{time_constraint}

{composition_rule}

{places_block}

【停留時間參考 — dur 欄位必須符合這個邏輯】
- 正餐（餐廳/小吃店）：60～90min
- 咖啡廳：45～60min
- 甜點店、手搖飲攤：10～20min（不要給 60min！）
- 散步、漫步消化、公園休息：20～30min
- 書店、選物店、逛街：30～45min
- 景點拍照：30～45min
- 酒吧、居酒屋、漫畫咖啡廳：60～90min

【時間】現在是 {current_time}。
各站預估到達時刻（每站平均45分鐘 + 移動10分鐘）：
{slot_time_hint(now_tw)}
⚠️ 有打烊時間的地點，「預估到達時刻 ＋ 本站 dur」必須 ≤ 打烊時間，否則絕對不能排入行程。
第一個地點 time 填 {current_time}，之後根據前一個地點 dur 累加計算。

請只回覆以下 JSON，不要有任何說明文字：
{{
  "title": "行程標題（10字以內，包含地區和主題）",
  "subtitle": "一句話描述氛圍（15字以內）",
  "items": [
    {{
      "time": "{current_time}",
      "dur": "60min",
      "activity": "清單中的完整地點名稱（不縮寫；散步/休息/買飲料也要填真實地點名，例如「大安森林公園」不要填「在附近散步」）",
      "desc": "一句話說明在這個地點要做什麼、有什麼特色（25字以內，例如：「吃完飯在這裡漫步消化，感受午後老街氛圍」）",
      "tag": "標籤（2～5字，如：散步消化、隱藏版甜點、宵夜必去、書香下午）",
      "dist": "步行 X 分鐘",
      "mood": "一個 emoji"
    }}
  ]
}}"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "你是台灣旅遊專家，只以 JSON 格式回覆，不加任何說明文字。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.75,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
