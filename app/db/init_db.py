"""
資料庫初始化 & seed。

流程：
1. CREATE EXTENSION postgis — 啟用地理空間功能 (第一次部署必做)
2. 依據 models/*.py 裡的定義建所有 table
3. 塞入盲盒行程 seed 資料 (從前端 mockData.js 搬過來)

呼叫時機：
- 開發時，docker compose up 後執行一次 `python -m app.db.init_db`
- 正式環境建議改用 Alembic migration
"""
import asyncio

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.db.base import Base
from app.db.models import TripItem, TripTemplate  # noqa: F401 — import 讓 metadata 認得 model


# ---------- 盲盒 seed 資料 ----------
# 直接對應前端 src/data/mockData.js，搬過來放 DB
SEED_TRIPS: list[dict] = [
    # ----- cafe -----
    {
        "vibe_key": "cafe", "title": "拜金",
        "items": [
            {"time": "13:30", "activity": "星巴克", "desc": "嘿嘿可以發限動了", "icon": "cafe", "color": "#84A6D3"},
            {"time": "15:30", "activity": "國北", "desc": "我愛慕虛榮啦！", "icon": "school", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "cafe", "title": "還在混啊",
        "items": [
            {"time": "19:30", "activity": "7-11", "desc": "買杯咖啡當心悸寶貝", "icon": "cafe", "color": "#C95E9E"},
            {"time": "19:40", "activity": "創意館", "desc": "連夜加班寫code", "icon": "walk", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "cafe", "title": "小聲點吵到我讀書了",
        "items": [
            {"time": "15:30", "activity": "路易莎", "desc": "喝咖啡聊是非", "icon": "cafe", "color": "#C3AED9"},
        ],
    },
    # ----- food -----
    {
        "vibe_key": "food", "title": "早餐吃到飽",
        "items": [
            {"time": "9:30", "activity": "好食早餐", "desc": "好那今天呢風光明媚風和日麗", "icon": "restaurant", "color": "#C95E9E"},
            {"time": "11:30", "activity": "和平時光", "desc": "連吃兩個早餐店，太無情了", "icon": "restaurant", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "food", "title": "我是義大利麵",
        "items": [
            {"time": "17:30", "activity": "I'm pasta", "desc": "我是義大利麵", "icon": "restaurant", "color": "#C95E9E"},
            {"time": "19:00", "activity": "回家的一路上", "desc": "回家吧孩子 回家吧", "icon": "home", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "food", "title": "藍藍路",
        "items": [
            {"time": "12:00", "activity": "麥當勞", "desc": "誰會在中午十二點吃麥當勞啊", "icon": "fast-food", "color": "#84A6D3"},
            {"time": "12:30", "activity": "創意館", "desc": "沒辦法內用好像只能去創館或學餐了(´・ω・`)", "icon": "school", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "food", "title": "增雞增脂",
        "items": [
            {"time": "17:30", "activity": "好吃雞排", "desc": "吃飽才有力氣減肥", "icon": "restaurant", "color": "#C95E9E"},
            {"time": "17:50", "activity": "combuy", "desc": "辛苦的一天犒賞自己一杯", "icon": "wine", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "food", "title": "餃浸醬汁",
        "items": [
            {"time": "12:00", "activity": "李記水餃", "desc": "哪裡可以領水餃，當舖，因為當舖領(dumplings)", "icon": "restaurant", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "food", "title": "乞丐超人",
        "items": [
            {"time": "20:00", "activity": "超商", "desc": "要是我的女人吃不到i珍食，你們都要給我陪葬", "icon": "restaurant", "color": "#C95E9E"},
        ],
    },
    {
        "vibe_key": "food", "title": "湯姆克滷汁",
        "items": [
            {"time": "19:00", "activity": "胖胖滷味", "desc": "到底叫胖胖還是財哥", "icon": "restaurant", "color": "#C95E9E"},
            {"time": "20:30", "activity": "回家家", "desc": "太晚了快回家", "icon": "home", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "food", "title": "米飯玄師",
        "items": [
            {"time": "11:50", "activity": "小圓村", "desc": "大杯飲料太多了根本喝不完", "icon": "restaurant", "color": "#84A6D3"},
            {"time": "12:40", "activity": "國北", "desc": "吃太飽散個步完去上課", "icon": "school", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "food", "title": "島揮！",
        "items": [
            {"time": "15:30", "activity": "搗飛", "desc": "挖欸能力丟洗島揮啊", "icon": "ice-cream", "color": "#C95E9E"},
            {"time": "16:30", "activity": "台大校園", "desc": "考不到至少可以在裡面散步", "icon": "school", "color": "#C3AED9"},
        ],
    },
    # ----- photo -----
    {
        "vibe_key": "photo", "title": "大安森靈感",
        "items": [
            {"time": "14:00", "activity": "大安森林公園", "desc": "賞花賞鳥賞老人", "icon": "leaf", "color": "#C3AED9"},
            {"time": "16:30", "activity": "蓁橙咖啡手作坊", "desc": "手機先吃(*´∀`)~", "icon": "cafe", "color": "#C95E9E"},
        ],
    },
    {
        "vibe_key": "photo", "title": "C門町",
        "items": [
            {"time": "11:30", "activity": "捷運科技大樓站", "desc": "前往西門", "icon": "bus", "color": "#C3AED9"},
            {"time": "12:00", "activity": "西門町", "desc": "就...逛西門町", "icon": "storefront", "color": "#C95E9E"},
        ],
    },
    {
        "vibe_key": "photo", "title": "不要遲到了",
        "items": [
            {"time": "9:20", "activity": "公車站", "desc": "前往台北當代藝術館", "icon": "bus", "color": "#84A6D3"},
            {"time": "10:00", "activity": "台北當代藝術館", "desc": "看展，遲到自己買票", "icon": "color-palette", "color": "#C3AED9"},
        ],
    },
    # ----- rain -----
    {
        "vibe_key": "rain", "title": "創館NPC",
        "items": [
            {"time": "14:20", "activity": "創意館", "desc": "在創館當npc或是與其他npc對話", "icon": "school", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "rain", "title": "受夠台北的天氣",
        "items": [
            {"time": "12:00", "activity": "星巴克", "desc": "遠離城市的喧囂", "icon": "color-palette", "color": "#C95E9E"},
            {"time": "15:00", "activity": "捷運科技大樓", "desc": "還在下雨就快點搭捷運逃離大安吧", "icon": "bus", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "rain", "title": "我怕練太壯",
        "items": [
            {"time": "13:00", "activity": "國北健身房", "desc": "跟著pizza葛格開練", "icon": "barbell", "color": "#C3AED9"},
            {"time": "14:30", "activity": "瑜伽墊上", "desc": "收操不然明天痛爆", "icon": "body", "color": "#C95E9E"},
        ],
    },
    {
        "vibe_key": "rain", "title": "我又沒有唸書",
        "items": [
            {"time": "13:00", "activity": "圖書館", "desc": "惡補考試或輕鬆看看書", "icon": "library", "color": "#84A6D3"},
        ],
    },
    # ----- walk -----
    {
        "vibe_key": "walk", "title": "嘿嘿種花",
        "items": [
            {"time": "13:30", "activity": "國北", "desc": "散步一邊種花", "icon": "walk", "color": "#84A6D3"},
            {"time": "14:30", "activity": "大安森林公園", "desc": "學校逛膩了換個地方", "icon": "walk", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "walk", "title": "舊城區發現案",
        "items": [
            {"time": "15:00", "activity": "大稻埕巷弄", "desc": "在舊房子間尋找未來", "icon": "map", "color": "#C3AED9"},
            {"time": "17:00", "activity": "碼頭夕陽", "desc": "這就是活著的感覺", "icon": "sunny", "color": "#C95E9E"},
        ],
    },
    {
        "vibe_key": "walk", "title": "走路靠右菩薩保佑",
        "items": [
            {"time": "14:20", "activity": "國北", "desc": "走路前往美術館", "icon": "walk", "color": "#84A6D3"},
            {"time": "14:40", "activity": "社區小公園", "desc": "逛逛展覽陶冶心靈", "icon": "color-palette", "color": "#C3AED9"},
        ],
    },
    # ----- gift -----
    {
        "vibe_key": "gift", "title": "忠孝東路走九遍",
        "items": [
            {"time": "13:30", "activity": "捷運科技大樓站", "desc": "忠孝復興gogo", "icon": "bus", "color": "#C95E9E"},
            {"time": "13:45", "activity": "忠孝sogo", "desc": "一輩子和我一起挑禮物嗎", "icon": "storefront", "color": "#C3AED9"},
        ],
    },
    {
        "vibe_key": "gift", "title": "勝利超人",
        "items": [
            {"time": "14:30", "activity": "勝立", "desc": "速速買", "icon": "storefront", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "gift", "title": "宅宅地下街",
        "items": [
            {"time": "17:00", "activity": "捷運科技大樓站", "desc": "北車速速妹", "icon": "bus", "color": "#C3AED9"},
            {"time": "17:30", "activity": "北車地下街", "desc": "北車地下街的價格好可怕", "icon": "storefront", "color": "#84A6D3"},
        ],
    },
    {
        "vibe_key": "gift", "title": "中山地下街",
        "items": [
            {"time": "17:00", "activity": "捷運科技大樓站", "desc": "中山速速妹", "icon": "bus", "color": "#84A6D3"},
            {"time": "17:30", "activity": "中山地下街", "desc": "買 買 買", "icon": "storefront", "color": "#C95E9E"},
        ],
    },
]


async def init_db() -> None:
    """建表 + seed。可重複執行，不會重複塞資料 (前會先檢查)。"""

    # 1. 啟用 PostGIS 擴充
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        print("[init_db] PostGIS 擴充已啟用")

        # 2. 依 models 定義建表
        await conn.run_sync(Base.metadata.create_all)
        print("[init_db] 所有資料表已建立")

    # 3. Seed 盲盒行程 (只在空表時塞)
    async with AsyncSessionLocal() as session:
        existing = await session.execute(text("SELECT COUNT(*) FROM trip_templates"))
        count = existing.scalar_one()
        if count > 0:
            print(f"[init_db] 已有 {count} 筆 trip_templates，跳過 seed")
            return

        for tpl in SEED_TRIPS:
            template = TripTemplate(vibe_key=tpl["vibe_key"], title=tpl["title"])
            for idx, item in enumerate(tpl["items"]):
                template.items.append(TripItem(order_index=idx, **item))
            session.add(template)

        await session.commit()
        print(f"[init_db] 已 seed {len(SEED_TRIPS)} 筆盲盒行程")


if __name__ == "__main__":
    asyncio.run(init_db())
