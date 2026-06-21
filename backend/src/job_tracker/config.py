"""應用設定，從環境變數 / .env 讀取。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "job_tracker"

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"

    # CORS（前端開發伺服器）
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
