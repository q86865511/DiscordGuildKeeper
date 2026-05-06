"""asyncio Redis client (redis-py).

Used for rate limiting (``/ask``, ``/summary`` — M4), scheduler locks (M3),
and short-lived caches. See PROJECT_SPEC.md §9.
"""

from __future__ import annotations

from typing import cast

import structlog
from redis.asyncio import Redis

_log = structlog.get_logger("butler.redis")


def create_redis(url: str) -> Redis:
    """Build a Redis client. Caller owns lifecycle (call ``.aclose()`` on shutdown)."""
    # redis-py's ``Redis.from_url`` returns ``Any`` in current stubs; cast to silence mypy.
    return cast(Redis, Redis.from_url(url, decode_responses=True, encoding="utf-8"))


async def ping_redis(client: Redis) -> bool:
    """Liveness probe for ``/readyz``. Returns ``False`` on any failure (logged)."""
    try:
        return bool(await client.ping())
    except Exception as exc:
        _log.warning("redis ping failed", error=str(exc), error_type=type(exc).__name__)
        return False
