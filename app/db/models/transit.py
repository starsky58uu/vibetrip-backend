"""
大眾運輸的「靜態資料」— 公車站、捷運站、YouBike 站。

為什麼放 PostgreSQL？
- 這些資料幾乎不會變（新設一站頂多幾個月一次）
- 需要「找最近的 X 站」→ PostGIS 一行 SQL 搞定，不用在 Python 寫距離公式
- 資料量不大（全台北大概幾千筆），完全塞得下

動態的即時到站時間、可借車數則放 Redis（見 redis_client.py）。

資料來源：TDX 平台。
→ 我們會寫個定期任務 (或手動一次性) 從 TDX 抓下來 seed 進這些 table。
"""
from typing import Optional,Any

from geoalchemy2 import Geography
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class BusStop(Base, UUIDPrimaryKey, TimestampMixin):
    """公車站牌。"""

    __tablename__ = "bus_stops"

    # TDX 給的 stop_id，全平台唯一
    tdx_stop_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # 該站會經過的路線（單一站牌通常會有多條路線，用逗號分隔簡化儲存）
    # 更嚴謹可建另一張 bus_stop_routes 中間表
    route_names: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )


class MrtStation(Base, UUIDPrimaryKey, TimestampMixin):
    """捷運站。"""

    __tablename__ = "mrt_stations"

    # TDX 給的 station_id (BL01, R02 ...)
    tdx_station_id: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # 路線代號：BL (板南), R (淡水信義), G (松山新店), O (中和新蘆), BR (文湖), Y (環狀)
    line_code: Mapped[str] = mapped_column(String(8), index=True, nullable=False)

    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )


class YoubikeStation(Base, UUIDPrimaryKey, TimestampMixin):
    """
    YouBike 站點（靜態部分 — 站點位置、總車格數）。

    注意：「目前可借/可還車輛數」是動態資料，不存這，存 Redis。
    這裡只存位置、名稱、總格位數等幾乎不會變的資訊。
    """

    __tablename__ = "youbike_stations"

    tdx_station_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # "1.0" 或 "2.0"
    bike_type: Mapped[str] = mapped_column(String(4), nullable=False, default="2.0")

    # 總車格數
    total_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 站點地址 (給使用者看的)
    address: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    __table_args__ = (Index("ix_youbike_name", "name"),)
