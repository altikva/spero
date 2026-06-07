# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# __creation__ = 2026-06-03
# __author__ = "jndjama (Joy Ndjama)"
# __copyright__ = "Copyright 2026 ALTIKVA."
# __licence__ = "MIT & CC BY-NC-SA (https://www.altikva.com/licenses/LICENSE-1.0)"
# -#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#-#
# Description: Runtime settings, loaded from environment (SPERO_*) or a .env file.

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
    # Bearer tokens for the HTTP surfaces. Empty = auth disabled (fine for a
    # localhost `serve`); set them to require `Authorization: Bearer <token>`.
    # `api_token` guards `spero serve`; `owner_token` guards `spero owner` and is
    # the one `spero agent` sends when it dials home.
    api_token: str = ""
    owner_token: str = ""
    # When true, scrub likely secrets/PII from event text before `spero ask` /
    # `spero diagnose` send it to the LLM (best-effort; see ai/redact.py).
    redact_events: bool = False
    # Alert channels. Empty = that channel is disabled. `slack_webhook_url` wins
    # over `alert_webhook_url` when both are set (see alerting.make_alerter); with
    # neither set, alerting falls back to NullAlerter.
    alert_webhook_url: str = ""
    slack_webhook_url: str = ""


settings = Settings()
