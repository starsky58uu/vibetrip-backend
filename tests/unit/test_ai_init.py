"""AI 子套件 re-export 測試。"""

from app.services.ai import generate_trip as pkg_generate
from app.services.ai.generator import generate_trip as mod_generate

assert pkg_generate is mod_generate
