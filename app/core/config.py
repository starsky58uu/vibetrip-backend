"""
專案設定中心 — 所有環境變數都在這裡集中管理。

設計原則：
- 使用 pydantic-settings 自動從環境變數 / .env 讀取
- 全專案共用同一個 settings 實例 (singleton)，不要在其他地方 os.getenv
- 敏感資訊 (密碼、API Key) 絕對不寫死在程式碼，全從 .env 讀
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---------- 基本資訊 ----------
    PROJECT_NAME: str = "VibeTrip API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # ---------- PostgreSQL ----------
    # 對應 docker-compose.yml 的 db service
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_USER: str = "tdx_user"
    DB_PASSWORD: str = "your_secure_password"
    DB_NAME: str = "tdx_database"

    @property
    def DATABASE_URL(self) -> str:
        """
        asyncpg 需要 postgresql+asyncpg:// 開頭的連線字串。
        這是 SQLAlchemy 2.0 異步模式的標準格式。
        """
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
    # 正式環境務必改成隨機長字串 (openssl rand -hex 32)
    JWT_SECRET_KEY: str = "change-me-in-production-please"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60          # access token 1 小時
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30            # refresh token 30 天

    # ---------- 外部 API ----------
    # TDX (交通部運輸資料流通服務平臺) — 公車/捷運/YouBike 即時資料
    TDX_CLIENT_ID: str = ""
    TDX_CLIENT_SECRET: str = ""

    # OpenWeatherMap — 天氣
    OPENWEATHER_API_KEY: str = ""

    # Google Maps — Places / Directions
    GOOGLE_MAPS_API_KEY: str = ""

    # Groq — 生成式 AI (LLaMA 3.3，免費額度比 Gemini 大 10 倍)
    GROQ_API_KEY: str = ""

    # ---------- 檔案上傳 ----------
    UPLOAD_DIR: str = "/app/uploads"                # 容器內路徑
    MAX_UPLOAD_SIZE_MB: int = 10
    PUBLIC_CDN_BASE: str = "http://localhost:8000/static/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """用 lru_cache 包起來，整個 App 共用同一個 Settings 實例。"""
    return Settings()


# 讓其他模組可以 from app.core.config import settings 直接取用
settings = get_settings()
