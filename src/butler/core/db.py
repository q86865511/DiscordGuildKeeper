"""Async PostgreSQL engine + session factory.

The engine and session factory are created once at process start (in
``butler.main``) and shared via :class:`butler.core.state.AppState`.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_log = structlog.get_logger("butler.db")


def create_engine(database_url: str) -> AsyncEngine:
    """Build an async engine. Caller owns lifecycle (call ``.dispose()`` on shutdown)."""
    return create_async_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``. Sessions don't expire on commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping_db(engine: AsyncEngine) -> bool:
    """Liveness probe for ``/readyz``. Returns ``False`` on any failure (logged)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        _log.warning("db ping failed", error=str(exc), error_type=type(exc).__name__)
        return False
    return True
