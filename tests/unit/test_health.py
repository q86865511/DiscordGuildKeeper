"""FastAPI ``/healthz``, ``/readyz``, ``/version`` endpoint tests.

DB / Redis ping helpers are monkey-patched so the routes exercise without a
live Postgres or Redis. The bot is a MagicMock with ``is_ready()`` toggled.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from butler.api.app import create_app
from butler.core.config import Settings
from butler.core.state import AppState


def _build_state(*, bot_ready: bool = True) -> AppState:
    bot = MagicMock()
    bot.is_ready.return_value = bot_ready
    return AppState(
        settings=Settings(_env_file=None),
        db_engine=MagicMock(),
        session_factory=MagicMock(),
        redis_client=MagicMock(),
        bot=bot,
    )


async def _ok(*_args: object, **_kwargs: object) -> bool:
    return True


async def _down(*_args: object, **_kwargs: object) -> bool:
    return False


def test_healthz_always_returns_ok() -> None:
    app = create_app(_build_state())
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_returns_app_version_and_git_sha() -> None:
    app = create_app(_build_state())
    with TestClient(app) as client:
        r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"]
    assert isinstance(body["git_sha"], str)
    assert body["git_sha"]


def test_readyz_all_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("butler.api.health.ping_db", _ok)
    monkeypatch.setattr("butler.api.health.ping_redis", _ok)
    app = create_app(_build_state(bot_ready=True))
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "discord": True,
        "postgres": True,
        "redis": True,
        "scheduler": True,
    }


def test_readyz_db_down_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("butler.api.health.ping_db", _down)
    monkeypatch.setattr("butler.api.health.ping_redis", _ok)
    app = create_app(_build_state(bot_ready=True))
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["postgres"] is False
    assert body["redis"] is True
    assert body["status"] == "degraded"


def test_readyz_redis_down_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("butler.api.health.ping_db", _ok)
    monkeypatch.setattr("butler.api.health.ping_redis", _down)
    app = create_app(_build_state(bot_ready=True))
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["redis"] is False


def test_readyz_bot_not_ready_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("butler.api.health.ping_db", _ok)
    monkeypatch.setattr("butler.api.health.ping_redis", _ok)
    app = create_app(_build_state(bot_ready=False))
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["discord"] is False


def test_readyz_no_bot_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("butler.api.health.ping_db", _ok)
    monkeypatch.setattr("butler.api.health.ping_redis", _ok)
    state = _build_state()
    state.bot = None  # API-only mode (no DISCORD_TOKEN)
    app = create_app(state)
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["discord"] is False
