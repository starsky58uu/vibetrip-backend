"""Settings 單元測試。"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_database_and_redis_urls() -> None:
    s = Settings(
        DB_HOST="localhost",
        DB_PORT=5432,
        DB_USER="u",
        DB_PASSWORD="p",
        DB_NAME="d",
        REDIS_HOST="redis",
        REDIS_PORT=6379,
        REDIS_DB=1,
    )
    assert "postgresql+asyncpg://u:p@localhost:5432/d" in s.DATABASE_URL
    assert s.REDIS_URL == "redis://redis:6379/1"


def test_cors_origins_wildcard() -> None:
    s = Settings(CORS_ORIGINS="*")
    assert s.cors_origins_list == ["*"]
    assert s.cors_allow_credentials is False


def test_cors_origins_list_parses_commas() -> None:
    s = Settings(CORS_ORIGINS="http://a.com, http://b.com")
    assert s.cors_origins_list == ["http://a.com", "http://b.com"]
    assert s.cors_allow_credentials is True


def test_production_rejects_default_jwt_secret(monkeypatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(DEBUG=False, JWT_SECRET_KEY="change-me-in-production-please")


def test_get_settings_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
