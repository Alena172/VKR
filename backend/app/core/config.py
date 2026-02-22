from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VKR English Learning API"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/vkr_db"
    ai_provider: str = "stub"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 1
    translation_strict_remote: bool = True
    jwt_secret: str = "change_me"
    jwt_issuer: str = "vkr"
    jwt_access_ttl_minutes: int = 60 * 24

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
