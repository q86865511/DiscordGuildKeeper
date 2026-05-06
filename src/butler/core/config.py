"""Application configuration via pydantic-settings.

Settings are populated from (in order):
  1. Process environment variables.
  2. ``.env`` file in the project root, if present.

Production (``APP_ENV=production``) requires ``DISCORD_TOKEN``, ``DATABASE_URL``,
and ``REDIS_URL`` to be set — startup fails fast if any is missing.
See PROJECT_SPEC.md §7.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed view of the bot's environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    json_logs: bool = True
    tz: str = "Asia/Taipei"

    # --- Discord ---
    discord_token: str | None = None
    discord_guild_id: int | None = None
    discord_admin_role_id: int | None = None
    discord_sync_commands: bool = True

    # --- LLM / Gemini ---
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_timeout_seconds: int = 60
    gemini_max_output_tokens: int = 1200

    # --- PostgreSQL ---
    postgres_user: str = "butler"
    postgres_password: str = "change-me"
    postgres_db: str = "butler"
    database_url: str = "postgresql+asyncpg://butler:change-me@postgres:5432/butler"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- FastAPI ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Scheduler ---
    anime_check_interval_minutes: int = 30
    ticket_check_interval_minutes: int = 10
    scheduler_lock_ttl_seconds: int = 900

    # --- Crawlers ---
    crawler_user_agent: str = "DiscordButlerBot/0.1 (+private friend guild)"
    http_timeout_seconds: int = 20
    http_retry_attempts: int = 2

    # --- Rate limits ---
    ask_daily_limit_per_user: int = 30
    summary_daily_limit_per_user: int = 10
    summary_max_messages: int = 200

    # --- M6+ Cloudflare Tunnel ---
    tunnel_token: str | None = None

    @model_validator(mode="after")
    def _require_critical_in_production(self) -> Self:
        if self.app_env != "production":
            return self
        missing: list[str] = []
        if not self.discord_token:
            missing.append("DISCORD_TOKEN")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.redis_url:
            missing.append("REDIS_URL")
        if missing:
            raise ValueError(f"production startup requires env vars: {', '.join(missing)}")
        return self


def load_settings() -> Settings:
    """Load and validate settings. Raises ``ValueError`` in misconfigured production."""
    return Settings()
