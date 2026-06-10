"""大眾運輸 schemas — 公車 / 捷運 / YouBike。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------- 公車 ----------
BusStatus = Literal["approaching", "in_transit", "departure", "no_service"]


class BusEtaResponse(BaseModel):
    route_name: str
    stop_name: str
    eta_seconds: int | None = Field(None, description="null 代表無車/末班已過")
    plate_number: str | None = None
    status: BusStatus
    fetched_at: datetime


# ---------- 捷運 ----------
class MrtTrainInfo(BaseModel):
    direction: str  # 往某終點站
    eta_seconds: int | None


class MrtEtaResponse(BaseModel):
    station_name: str
    next_trains: list[MrtTrainInfo]
    fetched_at: datetime


# ---------- YouBike ----------
class YoubikeStationResponse(BaseModel):
    station_id: str
    name: str
    latitude: float
    longitude: float
    distance_meters: float
    available_rent: int  # 可借車輛
    available_return: int  # 可還車位
    bike_type: str


class YoubikeListResponse(BaseModel):
    stations: list[YoubikeStationResponse]


# ---------- 路線規劃 ----------
TransportMode = Literal["walking", "transit_bus", "transit_mrt", "youbike"]


class RouteStep(BaseModel):
    instruction: str
    mode: TransportMode
    duration_seconds: int


class RouteOption(BaseModel):
    mode: TransportMode
    duration_seconds: int
    distance_meters: int
    available: bool
    steps: list[RouteStep] = Field(default_factory=list)
    reason: str | None = Field(None, description="available=False 時說明原因")


class DirectionsRequest(BaseModel):
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    modes: list[TransportMode] = Field(
        default_factory=lambda: ["walking", "transit_bus", "transit_mrt", "youbike"]
    )


class DirectionsResponse(BaseModel):
    routes: list[RouteOption]
