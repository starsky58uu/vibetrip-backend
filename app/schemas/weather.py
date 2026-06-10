"""天氣 schemas — current / forecast。"""

from datetime import datetime

from pydantic import BaseModel


class CurrentWeatherResponse(BaseModel):
    temperature: float
    feels_like: float
    condition: str  # Clear / Clouds / Rain ...
    description: str  # 中文描述
    icon: str  # OpenWeatherMap icon code, e.g. 01d
    humidity: int
    wind_speed: float
    pressure: int
    observed_at: datetime
    district: str | None = None
    greeting: str | None = None


class HourlyForecast(BaseModel):
    time: datetime
    temperature: float
    condition: str
    icon: str
    precipitation_prob: float


class DailyForecast(BaseModel):
    date: str  # YYYY-MM-DD
    temp_min: float
    temp_max: float
    condition: str
    icon: str


class ForecastResponse(BaseModel):
    hourly: list[HourlyForecast]
    daily: list[DailyForecast]
