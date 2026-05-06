"""FastAPI app factory.

The single :class:`AppState` instance is stashed on ``app.state.app_state`` so
route handlers can reach DB / Redis / the Discord bot via :func:`fastapi.Request`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from butler.api.health import router as health_router

if TYPE_CHECKING:
    from butler.core.state import AppState


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(
        title="Discord Butler Bot API",
        version=state.settings.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.app_state = state
    app.include_router(health_router)
    return app
