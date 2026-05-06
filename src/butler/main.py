"""Discord Butler Bot — process entry point.

Startup sequence (spec §4.2)
  1. Load + validate ``Settings``; configure structlog.
  2. Build DB engine + session factory + Redis client.
  3. Construct shared :class:`AppState`.
  4. Start FastAPI (uvicorn) as an asyncio task.
  5. If ``DISCORD_TOKEN`` is set, start the Discord client too; otherwise
     run API-only so ``/healthz`` keeps working.
  6. Wait for SIGINT / SIGTERM (or any task crash) and shut down in
     reverse order: Discord → API server → DB engine → Redis.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import TYPE_CHECKING

import structlog
import uvicorn

from butler.api.app import create_app as create_api_app
from butler.bot.client import ButlerBot
from butler.core.config import load_settings
from butler.core.db import create_engine, create_session_factory
from butler.core.logging import configure_logging
from butler.core.redis_client import create_redis
from butler.core.state import AppState
from butler.core.version import APP_VERSION, get_git_sha

if TYPE_CHECKING:
    from butler.core.config import Settings


class _NoSignalServer(uvicorn.Server):
    """Skip uvicorn's signal handlers; the lifecycle is managed by ``butler.main``."""

    def install_signal_handlers(self) -> None:  # pragma: no cover - trivial override
        return None


def _setup_signal_handlers(stop: asyncio.Event, log: structlog.stdlib.BoundLogger) -> None:
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        if not stop.is_set():
            log.info("shutdown signal received")
            stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Not supported on every platform (e.g. Windows ProactorEventLoop).
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _request_stop)


async def _run() -> None:
    settings: Settings = load_settings()
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    log = structlog.get_logger("butler.main")

    log.info(
        "starting Discord Butler Bot",
        app_version=APP_VERSION,
        git_sha=get_git_sha(),
        app_env=settings.app_env,
    )

    # --- Build runtime resources ---
    db_engine = create_engine(settings.database_url)
    session_factory = create_session_factory(db_engine)
    redis_client = create_redis(settings.redis_url)

    state = AppState(
        settings=settings,
        db_engine=db_engine,
        session_factory=session_factory,
        redis_client=redis_client,
    )

    # --- FastAPI server ---
    api_app = create_api_app(state)
    server_config = uvicorn.Config(
        api_app,
        host=settings.api_host,
        port=settings.api_port,
        # Use our structlog setup; uvicorn's own access log would double-print.
        log_config=None,
        access_log=False,
    )
    server = _NoSignalServer(server_config)

    # --- Discord client (only when configured) ---
    bot: ButlerBot | None = None
    token = settings.discord_token
    if token:
        bot = ButlerBot(state=state)
        state.bot = bot
        log.info("Discord token detected — bot will connect to gateway")
    else:
        log.warning(
            "DISCORD_TOKEN not set — running API server only (no Discord)",
        )

    # --- Schedule tasks ---
    stop = asyncio.Event()
    _setup_signal_handlers(stop, log)

    server_task: asyncio.Task[None] = asyncio.create_task(server.serve(), name="api")
    bot_task: asyncio.Task[None] | None = None
    if bot is not None and token:
        bot_task = asyncio.create_task(bot.start(token), name="discord")

    def _on_task_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            log.error(
                "task crashed",
                task=task.get_name(),
                error_type=type(exc).__name__,
                error=str(exc),
            )
        else:
            log.info("task exited cleanly", task=task.get_name())
        if not stop.is_set():
            stop.set()

    server_task.add_done_callback(_on_task_done)
    if bot_task is not None:
        bot_task.add_done_callback(_on_task_done)

    log.info(
        "ready",
        api_host=settings.api_host,
        api_port=settings.api_port,
        discord_enabled=bot is not None,
    )

    await stop.wait()
    log.info("shutting down")

    # --- Shutdown sequence (spec §4.3) ---
    # 1. Stop accepting new commands by closing Discord first.
    if bot is not None:
        try:
            await bot.close()
        except Exception as exc:
            log.warning("bot.close() raised", error=str(exc))

    # 2. Tell uvicorn to drain.
    server.should_exit = True

    pending: list[asyncio.Task[None]] = [
        t for t in (server_task, bot_task) if t is not None and not t.done()
    ]
    if pending:
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending, return_exceptions=True),
                timeout=10,
            )
        except TimeoutError:
            log.warning("tasks did not finish in 10s; cancelling")
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    # 3. Dispose DB engine.
    log.info("disposing DB engine")
    await db_engine.dispose()

    # 4. Close Redis.
    log.info("closing Redis")
    with contextlib.suppress(Exception):
        await redis_client.aclose()

    log.info("shutdown complete")


def main() -> None:
    """Console entry point — runs the async bot lifecycle to completion."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
