"""``command_invocations`` write helper.

Failures are logged and swallowed: a downed DB must not break the user-facing
slash-command response. Spec §3 (observability) and §25 (quality).
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from butler.models.usage import CommandInvocation

_log = structlog.get_logger("butler.repositories.usage")


async def record_invocation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interaction_id: int | None,
    guild_id: int | None,
    channel_id: int | None,
    user_id: int | None,
    command_name: str,
    status: str,
    latency_ms: int | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """Persist one row to ``command_invocations``."""
    try:
        async with session_factory() as session:
            session.add(
                CommandInvocation(
                    interaction_id=interaction_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    command_name=command_name,
                    status=status,
                    latency_ms=latency_ms,
                    error_type=error_type,
                    error_message=error_message,
                )
            )
            await session.commit()
    except Exception as exc:
        _log.warning(
            "failed to record command invocation",
            command_name=command_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
