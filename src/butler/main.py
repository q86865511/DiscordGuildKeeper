"""Discord Butler Bot — process entry point.

M0 behaviour
------------
1. Load + validate ``Settings``.
2. Configure structlog (JSON by default).
3. Emit a startup banner.
4. Idle until SIGINT / SIGTERM — no Discord, DB, Redis, or HTTP server yet.

M1+ will wire the real lifecycle here (Discord client, FastAPI health server,
APScheduler) following PROJECT_SPEC.md §4.2.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import TYPE_CHECKING

import structlog

from butler.core.config import load_settings
from butler.core.logging import configure_logging
from butler.core.version import APP_VERSION, get_git_sha

if TYPE_CHECKING:
    from butler.core.config import Settings


async def _idle_until_terminated(log: structlog.stdlib.BoundLogger) -> None:
    """Block until SIGINT / SIGTERM is received (or the loop is cancelled)."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_stop() -> None:
        if not stop.is_set():
            log.info("shutdown signal received")
            stop.set()

    # Signal handlers are not supported on every platform (e.g. Windows
    # ProactorEventLoop). The bot still responds to KeyboardInterrupt there.
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, _request_stop)

    await stop.wait()


async def _run() -> None:
    settings: Settings = load_settings()
    configure_logging(level=settings.log_level, json_logs=settings.json_logs)

    log = structlog.get_logger("butler.main")
    log.info(
        "starting Discord Butler Bot",
        app_version=APP_VERSION,
        git_sha=get_git_sha(),
        app_env=settings.app_env,
        log_level=settings.log_level,
        json_logs=settings.json_logs,
    )

    if settings.discord_token:
        log.info("Discord token detected — Discord lifecycle will start at M1")
    else:
        log.warning("DISCORD_TOKEN not set; idling (M0 placeholder behaviour)")

    log.info("entering idle loop", reason="awaiting SIGINT/SIGTERM")
    await _idle_until_terminated(log)
    log.info("shutdown complete")


def main() -> None:
    """Console entry point — runs the async bot lifecycle to completion."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
