"""structlog configuration.

All output goes to stdout. Production uses JSON (one event per line); local dev
can opt into the pretty console renderer by setting ``JSON_LOGS=false``.

stdlib loggers (uvicorn, discord.py, asyncio, etc.) are routed through the same
formatter so the entire process emits a single, consistent stream.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import Processor


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog + stdlib logging. Safe to call multiple times."""
    log_level = _parse_level(level)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ExtraAdder(),
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(log_level)


def _parse_level(level: str) -> int:
    parsed = logging.getLevelName(level.upper())
    return parsed if isinstance(parsed, int) else logging.INFO
