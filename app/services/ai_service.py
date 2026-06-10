"""
AI 行程生成服務（facade）。

實作已拆分至 app.services.ai 子模組。
"""

from app.services.ai.generator import generate_trip
from app.services.ai.validation import validate_activities as _validate_activities

__all__ = ["generate_trip", "_validate_activities"]
