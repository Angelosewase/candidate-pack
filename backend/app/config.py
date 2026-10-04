from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
    """All configuration comes from environment variables (12-factor style)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://desk:desk@localhost:5432/desk"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_ttl_minutes: int = 8 * 60
    log_level: str = "INFO"
    # Max accepted CSV upload size; protects the API from memory exhaustion.
    max_import_bytes: int = 50 * 1024 * 1024

    @model_validator(mode="after")
    def _refuse_dev_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
