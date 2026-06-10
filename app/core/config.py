"""
專案設定中心 — 所有環境變數都在這裡集中管理。

設計原則：
- 使用 pydantic-settings 自動從環境變數 / .env 讀取
- 全專案共用同一個 settings 實例 (singleton)，不要在其他地方 os.getenv
- 敏感資訊 (密碼、API Key) 絕對不寫死在程式碼，全從 .env 讀
"""

from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_DEFAULT = "change-me-in-production-please"


class Settings(BaseSettings):
    # ---------- 基本資訊 ----------
    PROJECT_NAME: str = "VibeTrip API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # 逗號分隔的允許來源；開發可設 *（不帶 credentials）
    CORS_ORIGINS: str = "*"

    # ---------- PostgreSQL ----------
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_USER: str = "tdx_user"
    DB_PASSWORD: str = "your_secure_password"
    DB_NAME: str = "tdx_database"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ---------- Redis ----------
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ---------- JWT ----------
    JWT_SECRET_KEY: str = _INSECURE_JWT_DEFAULT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ---------- 外部 API ----------
    TDX_CLIENT_ID: str = ""
    TDX_CLIENT_SECRET: str = ""

    OPENWEATHER_API_KEY: str = ""

    # 支援 GOOGLE_MAPS_API_KEY 或舊名 GOOGLE_API_KEY
    GOOGLE_MAPS_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY"),
    )

    GROQ_API_KEY: str = ""

    # ---------- 檔案上傳 ----------
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    PUBLIC_CDN_BASE: str = "http://localhost:8000/static/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        # 瀏覽器規範：allow_origins=["*"] 時不可帶 credentials
        return "*" not in self.cors_origins_list

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if not self.DEBUG and self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT:
            raise ValueError(
                "JWT_SECRET_KEY 仍為預設值；正式環境請在 .env 設定隨機字串 (openssl rand -hex 32)"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
