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
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    cors_allow_origin_regex: str | None = r"^https://.*\.ngrok-free\.dev$"
    trusted_hosts: str = "localhost,127.0.0.1,backend,gateway,*.ngrok-free.dev"
    # Celery / Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_allow_origins_list(self) -> list[str]:
        values = [item.strip() for item in self.cors_allow_origins.split(",")]
        return [item for item in values if item]

    @property
    def trusted_hosts_list(self) -> list[str]:
        values = [item.strip() for item in self.trusted_hosts.split(",")]
        return [item for item in values if item]


@lru_cache
def get_settings() -> Settings:
    return Settings()
