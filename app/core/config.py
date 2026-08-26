from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    project_name: str = "Portfolio API"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    contact_to_email: str = "you@example.com"

    hevy_api_key: str | None = None
    hevy_api_base_url: str = "https://api.hevyapp.com/v1"
    hevy_cache_ttl_seconds: int = 3600
    hevy_timezone: str = "Asia/Kolkata"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def hevy_configured(self) -> bool:
        return bool(self.hevy_api_key and self.hevy_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
