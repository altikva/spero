"""Runtime settings, loaded from environment (SPERO_*) or a .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPERO_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///spero.db"
    policy_path: str = "policies/example.yaml"
    host: str = "127.0.0.1"
    port: int = 8800
    log_level: str = "INFO"


settings = Settings()
