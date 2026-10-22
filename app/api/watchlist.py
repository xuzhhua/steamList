"""Watchlist CRUD endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import WatchItem, WatchState
from ..schemas import (
    AddWatchRequest,
    PatchWatchRequest,
    WatchItemOut,
    WatchlistResponse,
    WatchlistSummary,
    WishlistImportRequest,
    WishlistImportResponse,
)
from ..services.pricing import ensure_game, ensure_placeholder_game, ingest_prices
from ..services.settings_store import get_settings as load_settings, update_settings
from ..services.steam_client import SteamError, SteamClient
from ..services.wishlist import import_wishlist
from ..timeutil import to_iso, utcnow
from .common import run_client_work
from .serializers import watch_item_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _get_item(db: Session, appid: int) -> WatchItem:
    item = db.execute(select(WatchItem).where(WatchItem.appid == appid)).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail=f"appid {appid} is not on the watchlist")
    return item


@router.get("", response_model=WatchlistResponse)
def list_watchlist(db: Session = Depends(get_db)) -> WatchlistResponse:
    rows = db.execute(select(WatchItem).order_by(WatchItem.sort_order, WatchItem.id)).scalars().all()
    items = [watch_item_out(db, row) for row in rows]
    summary = WatchlistSummary(
        count=len(items),
        discounting_count=sum(1 for i in items if i.available and i.current_discount_percent > 0),
        atl_count=sum(1 for i in items if i.atl_cents is not None),
        below_target_count=sum(
            1
            for i in items
            if i.available
            and i.target_price_cents is not None
            and i.current_final_cents > 0
            and i.current_final_cents <= i.target_price_cents
        ),
        last_checked_at=max((i.last_checked_at for i in items if i.last_checked_at), default=None),
    )
    return WatchlistResponse(items=items, summary=summary)


@router.post("", response_model=WatchItemOut, status_code=201)
def add_watch(
    payload: AddWatchRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> WatchItemOut:
    existing = db.execute(select(WatchItem).where(WatchItem.appid == payload.appid)).scalar_one_or_none()
    if existing is not None:
        response.status_code = 200
        return watch_item_out(db, existing)

    settings = load_settings(db)
    cc = (payload.cc or settings["cc"]).lower()
    max_sort = db.execute(select(func.max(WatchItem.sort_order))).scalar() or 0

    ensure_placeholder_game(db, payload.appid)
    item = WatchItem(
        appid=payload.appid,
        cc=cc,
        target_price_cents=payload.target_price_cents,
        discount_alert_threshold=payload.discount_alert_threshold,
        note=payload.note,
        notify_enabled=payload.notify_enabled,
        sort_order=max_sort + 10,
    )
    db.add(item)
    db.flush()

    try:
        meta, price = run_client_work(
            request.app, cc, settings["lang"], lambda client: client.fetch_app(payload.appid)
        )
    except SteamError as exc:
        logger.warning("steam fetch failed for appid %s: %s", payload.appid, exc)
        meta, price = None, None

    if meta is not None:
        ensure_game(db, meta)
    if price is not None:
        ingest_prices(db, {payload.appid: price}, cc)
    db.commit()
    db.refresh(item)
    return watch_item_out(db, item)


@router.patch("/{appid}", response_model=WatchItemOut)
def patch_watch(appid: int, payload: PatchWatchRequest, db: Session = Depends(get_db)) -> WatchItemOut:
    item = _get_item(db, appid)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return watch_item_out(db, item)


@router.delete("/{appid}", status_code=204)
def delete_watch(appid: int, db: Session = Depends(get_db)) -> Response:
    item = _get_item(db, appid)
    db.query(WatchState).filter(WatchState.appid == appid).delete()
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.post("/import", response_model=WishlistImportResponse)
def import_steam_wishlist(
    payload: WishlistImportRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> WishlistImportResponse:
    settings = load_settings(db)
    steamid = (payload.steamid or str(settings.get("steamid") or "")).strip()
    if not steamid:
        raise HTTPException(status_code=400, detail="steamid is required (pass it or save it in settings)")

    cc = str(settings["cc"])

    async def work(client: SteamClient):
        resolved = await client.resolve_steamid(steamid)
        ids = [int(appid) for appid in (await client.fetch_wishlist(resolved))][: payload.limit]
        if not ids:
            profile = await client.fetch_profile(resolved)
            visibility = await client.wishlist_visibility(resolved)
            return resolved, ids, {}, {}, profile, visibility
        prices = await client.fetch_prices(ids)
        metas = await client.fetch_metas(ids)
        return resolved, ids, prices, metas, None, ""

    try:
        resolved_steamid, appids, prices, metas, profile, visibility = run_client_work(
            request.app, cc, str(settings["lang"]), work
        )
    except SteamError as exc:
        logger.warning("wishlist import failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"steam wishlist fetch failed: {exc}") from exc

    errors: list[str] = []
    if not appids:
        errors.append(_empty_wishlist_reason(resolved_steamid, profile, visibility))
    report = import_wishlist(db, appids, metas, prices, cc)
    update_settings(db, {"wishlist_last_import_at": to_iso(utcnow()), "steamid": resolved_steamid})
    db.commit()

    return WishlistImportResponse(
        imported=report.imported,
        skipped=report.skipped,
        failed=report.failed,
        total=len(appids),
        appids=report.appids,
        errors=errors,
    )


def _empty_wishlist_reason(
    steamid: str,
    profile: dict[str, str] | None,
    visibility: str,
) -> str:
    """Explain why GetWishlist returned nothing, with an actionable next step."""
    if not profile:
        return f"找不到 SteamID {steamid} 对应的个人资料，请检查 ID 或链接是否正确"
    persona = profile.get("persona") or steamid
    privacy = profile.get("privacy") or ""
    if visibility == "hidden" or privacy != "public":
        reason = f"当前资料隐私：{privacy}" if privacy else "隐私设置限制了公开访问"
        return (
            f"「{persona}」的 Steam 心愿单不可见（{reason}）。"
            "请打开 Steam → 个人资料 → 编辑个人资料 → 隐私设置，"
            "把「我的个人资料」设为「公开」（如有「心愿单」选项也设为公开），保存后重试导入。"
        )
    return f"「{persona}」的个人资料已公开，但心愿单里没有游戏（或心愿单被隐藏），请先在 Steam 添加游戏到心愿单"


def client_factory(app, cc: str, lang: str) -> SteamClient:  # pragma: no cover - typing helper
    return app.state.steam_factory(cc, lang)
