"""應用設定，從環境變數 / .env 讀取。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "job_tracker"

    # LLM provider 選擇：openrouter | azure | foundry | anthropic
    llm_provider: str = "openrouter"

    # OpenRouter（OpenAI 相容，預設用免費模型）
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "qwen/qwen3-next-80b-a3b-instruct:free"

    # Azure OpenAI
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""  # 例：https://<your-resource>.openai.azure.com
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = "gpt-4o-mini"  # Azure 上的 deployment 名稱

    # Microsoft Foundry（Azure 上的 Claude，原生 Anthropic API）
    foundry_api_key: str = ""
    foundry_base_url: str = ""  # 例：https://<resource>.services.ai.azure.com/anthropic
    foundry_model: str = "claude-sonnet-4-6"  # Azure 上的 deployment 名稱

    # Anthropic（原生 structured outputs）
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # CORS：逗號分隔的允許來源（部署時加上前端正式網域）
    allowed_origins: str = "http://localhost:5173"

    # Logging
    log_level: str = "INFO"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
