"""
v1 API 總路由 — 掛載各模組的 sub-router。

所有端點最終都會帶有 /api/v1 前綴 (見 main.py)。
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    blindbox,      # 舊的測試端點，保留
    directions,
    places,
    spots,
    taste,
    transit,
    trips,
    uploads,
    users,
    weather,
)


api_router = APIRouter()

# ---------- 認證 / 使用者 ----------
api_router.include_router(auth.router, prefix="/auth", tags=["認證"])
api_router.include_router(users.router, prefix="/users", tags=["使用者"])

# ---------- 盲盒行程 ----------
api_router.include_router(trips.router, prefix="/trips", tags=["盲盒行程"])
api_router.include_router(blindbox.router, prefix="/blindbox", tags=["盲盒 (舊測試)"])

# ---------- 天氣 ----------
api_router.include_router(weather.router, prefix="/weather", tags=["天氣"])

# ---------- 地點 / 路線 / 大眾運輸 ----------
api_router.include_router(places.router, prefix="/places", tags=["地點搜尋"])
api_router.include_router(transit.router, prefix="/transit", tags=["大眾運輸"])
api_router.include_router(directions.router, prefix="/directions", tags=["路線規劃"])

# ---------- 足跡 ----------
api_router.include_router(spots.router, prefix="/spots", tags=["足跡"])

# ---------- 上傳 ----------
api_router.include_router(uploads.router, prefix="/uploads", tags=["上傳"])

# ---------- AI 口味分析 ----------
api_router.include_router(taste.router, prefix="/taste", tags=["口味分析"])
