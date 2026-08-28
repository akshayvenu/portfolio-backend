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

    # Hevy answers 429 past roughly 5 requests/second; a snapshot build is ~25 paged
    # requests, so it is throttled and retried rather than allowed to burst.
    hevy_requests_per_second: float = 3.0
    hevy_request_burst: int = 4
    hevy_max_retries: int = 3
    hevy_template_cache_ttl_seconds: int = 86_400
    # A failed build is only cached briefly, so one 429 does not pin the page to
    # fallback data for a whole hevy_cache_ttl_seconds.
    hevy_fallback_cache_ttl_seconds: int = 120

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def hevy_configured(self) -> bool:
        return bool(self.hevy_api_key and self.hevy_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
