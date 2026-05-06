"""``/healthz``, ``/readyz``, ``/version`` endpoints. Spec §14.1.

- ``/healthz`` always returns 200 if the asyncio loop is serving requests
  (used by Docker healthcheck).
- ``/readyz`` returns 200 only when DB, Redis, scheduler, and Discord client
  are all live; otherwise 503.
- ``/version`` exposes the app version + git sha.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from butler.core.db import ping_db
from butler.core.redis_client import ping_redis
from butler.core.version import APP_VERSION, get_git_sha

if TYPE_CHECKING:
    from butler.core.state import AppState

router = APIRouter()


class HealthzResponse(BaseModel):
    status: str


class ReadyzResponse(BaseModel):
    status: str
    discord: bool
    postgres: bool
    redis: bool
    scheduler: bool


class VersionResponse(BaseModel):
    version: str
    git_sha: str


def _state(request: Request) -> AppState:
    state: AppState = request.app.state.app_state
    return state


@router.get("/healthz", response_model=HealthzResponse)
async def healthz() -> HealthzResponse:
    return HealthzResponse(status="ok")


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    state = _state(request)
    bot = state.bot
    discord_ready = bool(bot is not None and bot.is_ready())
    db_ok = await ping_db(state.db_engine)
    redis_ok = await ping_redis(state.redis_client)
    scheduler_ok = True  # M3 will replace this with the real check.

    all_ready = discord_ready and db_ok and redis_ok and scheduler_ok
    payload = ReadyzResponse(
        status="ok" if all_ready else "degraded",
        discord=discord_ready,
        postgres=db_ok,
        redis=redis_ok,
        scheduler=scheduler_ok,
    )
    return JSONResponse(
        payload.model_dump(),
        status_code=200 if all_ready else 503,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(version=APP_VERSION, git_sha=get_git_sha())
