"""Helpers shared by API routers that need the Steam client."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import FastAPI

from ..services.steam_client import SteamClient


async def _run(factory: Callable[..., SteamClient], cc: str, lang: str, work) -> Any:
    client = factory(cc, lang)
    try:
        return await work(client)
    finally:
        await client.aclose()


def run_client_work(app: FastAPI, cc: str, lang: str, work: Callable[[SteamClient], Awaitable[Any]]) -> Any:
    """Run an async Steam call from a sync (threadpool) endpoint."""
    factory = app.state.steam_factory
    return asyncio.run(_run(factory, cc, lang, work))
