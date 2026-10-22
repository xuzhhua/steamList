"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import games, health, settings as settings_api, watchlist
from .config import Settings, get_settings
from .db import Database
from .services.steam_client import SteamClient

logger = logging.getLogger("steamlist")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_dirs()
    logging.basicConfig(level=settings.log_level)

    database = Database(settings.db_path)
    database.create_all()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        scheduler = getattr(application.state, "scheduler", None)
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown()
            database.dispose()

    app = FastAPI(
        title="SteamList",
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = database

    def steam_factory(cc: str, lang: str) -> SteamClient:
        return SteamClient(cc=cc, lang=lang, proxy=settings.proxy_url or None)

    app.state.steam_factory = steam_factory

    app.include_router(health.router, prefix="/api")
    app.include_router(watchlist.router, prefix="/api")
    app.include_router(games.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA from app/static with history fallback."""
    index = STATIC_DIR / "index.html"
    if not index.exists():
        logger.info("frontend bundle not found at %s; API-only mode", STATIC_DIR)
        return

    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "docs")):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
