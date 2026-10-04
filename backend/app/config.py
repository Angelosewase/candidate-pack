"""Application configuration (12-factor: environment variables only).

All settings are read once at startup via the ``get_settings()`` cached factory.
For local development outside Docker, values come from ``backend/.env``.
For Docker Compose, they come from the ``environment:`` block in compose.yml.
"""

from functools import lru_cache
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
    """All configuration comes from environment variables (12-factor style)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # SQLAlchemy connection URL. Required in production.
    database_url: str = "postgresql+psycopg://desk:desk@localhost:5432/desk"

    # JWT signing secret. MUST be overridden in production.
    jwt_secret: str = DEV_JWT_SECRET

    # Access-token lifetime in minutes (default: 8 hours).
    jwt_ttl_minutes: int = 8 * 60

    # Logging level passed to Python's logging module.
    log_level: str = "INFO"

    # Maximum accepted CSV upload size in bytes (default: 50 MB).
    max_import_bytes: int = 50 * 1024 * 1024

    # Comma-separated list of allowed CORS origins. Defaults to "*" (dev only).
    # Example: "https://desk.example.com,https://admin.example.com"
    cors_origins: list[str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _refuse_dev_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
