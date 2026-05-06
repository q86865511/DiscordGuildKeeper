"""M0 smoke tests — verify the skeleton boots and primitives behave."""

from __future__ import annotations

import json

import pytest
import structlog

from butler import APP_VERSION as PACKAGE_VERSION
from butler.core.config import Settings
from butler.core.logging import configure_logging
from butler.core.version import APP_VERSION, get_git_sha


def _clear_butler_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe any Butler-related env that might leak from the host shell."""
    keys = [
        "APP_ENV",
        "DISCORD_TOKEN",
        "DATABASE_URL",
        "REDIS_URL",
        "GEMINI_API_KEY",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_package_exports_version() -> None:
    assert PACKAGE_VERSION == APP_VERSION
    assert isinstance(APP_VERSION, str)
    assert APP_VERSION


def test_get_git_sha_returns_non_empty_string() -> None:
    sha = get_git_sha()
    assert isinstance(sha, str)
    assert sha
    # Either a real sha (12 hex chars) or the explicit fallback
    assert sha == "unknown" or len(sha) == 12


def test_settings_dev_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_butler_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.discord_token is None
    assert settings.gemini_model == "gemini-2.5-flash-lite"
    assert settings.api_port == 8000
    assert settings.json_logs is True


def test_settings_production_requires_discord_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_butler_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Settings(_env_file=None)


def test_settings_production_with_required_envs_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_butler_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DISCORD_TOKEN", "token-xyz")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    settings = Settings(_env_file=None)
    assert settings.discord_token == "token-xyz"
    assert settings.app_env == "production"


def test_configure_logging_json_emits_one_event_per_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_logs=True)
    structlog.get_logger("butler.test").info("hello", marker=42)
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "expected at least one log line on stdout"
    payload = json.loads(captured[-1])
    assert payload["event"] == "hello"
    assert payload["marker"] == 42
    assert payload["level"] == "info"
    assert payload["logger"] == "butler.test"
    assert "timestamp" in payload


def test_configure_logging_console_renderer_does_not_crash(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="DEBUG", json_logs=False)
    structlog.get_logger("butler.test").info("dev render", foo="bar")
    out = capsys.readouterr().out
    assert "dev render" in out


def test_configure_logging_idempotent() -> None:
    configure_logging(level="INFO", json_logs=True)
    configure_logging(level="DEBUG", json_logs=False)
    configure_logging(level="INFO", json_logs=True)
    # No assertion — just verifying repeated configuration does not raise


def test_main_module_importable() -> None:
    """``python -m butler.main`` resolves; importing must not execute the loop."""
    import butler.main as main_module

    assert callable(main_module.main)
