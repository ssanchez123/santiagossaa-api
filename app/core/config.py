"""Application configuration."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Santiago API"
    app_description: str = "Self-hosted FastAPI with Docker, Cloudflare Tunnel, and automated CI/CD"
    app_version: str = "1.0.0"
    environment: str = Field(default="development", alias="ENV")
    debug: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()