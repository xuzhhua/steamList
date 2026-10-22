"""Game metadata, price series and statistics endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Game, WatchItem
from ..schemas import (
    GameDetailResponse,
    SearchItemOut,
    SearchResponse,
    SeriesPointOut,
    SeriesResponse,
    StatsResponse,
)
from ..services.analytics import build_series, compute_stats, load_points, range_start
from ..services.settings_store import get_settings as load_settings
from ..services.steam_client import SteamError
from ..timeutil import to_iso, utcnow
from .common import run_client_work
from .serializers import game_out, watch_item_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


def _watch(db: Session, appid: int) -> WatchItem:
    item = db.execute(select(WatchItem).where(WatchItem.appid == appid)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail=f"appid {appid} is not on the watchlist")
    return item


def _record_started(db: Session, appid: int) -> str | None:
    from ..models import WatchState

    state = db.get(WatchState, appid)
    return to_iso(state.first_change_at) if state else None


@router.get("/search", response_model=SearchResponse)
def search_games(
    request: Request,
    term: str = Query(default=""),
    db: Session = Depends(get_db),
) -> SearchResponse:
    term = term.strip()
    if len(term) < 2:
        raise HTTPException(status_code=400, detail="search term must be at least 2 characters")
    settings = load_settings(db)
    try:
        items = run_client_work(
            request.app,
            settings["cc"],
            settings["lang"],
            lambda client: client.search(term, limit=12),
        )
    except SteamError as exc:
        logger.warning("steam search failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"steam search failed: {exc}") from exc
    return SearchResponse(
        items=[
            SearchItemOut(
                appid=i.appid,
                name=i.name,
                header_image=i.header_image,
                price_cents=i.price_cents,
                currency=i.currency,
            )
            for i in items
        ]
    )


@router.get("/{appid}", response_model=GameDetailResponse)
def game_detail(appid: int, db: Session = Depends(get_db)) -> GameDetailResponse:
    item = _watch(db, appid)
    game = db.get(Game, appid)
    if game is None:
        raise HTTPException(status_code=404, detail=f"game {appid} not found")
    return GameDetailResponse(game=game_out(game), watch=watch_item_out(db, item))


@router.get("/{appid}/series", response_model=SeriesResponse)
def game_series(
    appid: int,
    range: str = Query(default="all"),  # noqa: A002 - matches the public API
    db: Session = Depends(get_db),
) -> SeriesResponse:
    item = _watch(db, appid)
    now = utcnow()
    try:
        start = range_start(range, now)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unsupported range: {range}") from exc

    points = load_points(db, appid, item.cc)
    series = build_series(points, start, now)
    from ..models import WatchState

    state = db.get(WatchState, appid)
    return SeriesResponse(
        appid=appid,
        range=range,
        start=to_iso(start),
        end=to_iso(now) or "",
        points=[SeriesPointOut(**point) for point in series],
        record_started_at=to_iso(state.first_change_at) if state else None,
        currency=state.currency if state else "",
    )


@router.get("/{appid}/stats", response_model=StatsResponse)
def game_stats(appid: int, db: Session = Depends(get_db)) -> StatsResponse:
    item = _watch(db, appid)
    points = load_points(db, appid, item.cc)
    return StatsResponse(
        appid=appid,
        stats=compute_stats(points, utcnow()),
        record_started_at=_record_started(db, appid),
    )
