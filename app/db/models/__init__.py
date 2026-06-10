"""
集中 import 所有 models，讓 Base.metadata 認得它們。
init_db 時就能一次建好全部 table。
"""

from app.db.models.spot import CommunitySpot, PersonalSpot, SpotLike, SpotSave
from app.db.models.transit import BusStop, MrtStation, YoubikeStation
from app.db.models.trip import TripItem, TripTemplate
from app.db.models.user import User

__all__ = [
    "User",
    "TripTemplate",
    "TripItem",
    "PersonalSpot",
    "CommunitySpot",
    "SpotLike",
    "SpotSave",
    "BusStop",
    "MrtStation",
    "YoubikeStation",
]
