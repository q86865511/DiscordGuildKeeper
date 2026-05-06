"""Shared application state.

A single :class:`AppState` is constructed in ``butler.main`` and threaded
through both the Discord bot and the FastAPI app. Routes / cogs reach the
runtime resources via this object instead of importing module-level globals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from butler.core.config import Settings

if TYPE_CHECKING:
    from butler.bot.client import ButlerBot


@dataclass
class AppState:
    """Container for runtime resources shared across the process."""

    settings: Settings
    db_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis_client: Redis
    bot: ButlerBot | None = None
