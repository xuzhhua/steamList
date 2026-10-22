"""Convert ORM rows into API response models."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, JobRun, NotificationChannel, WatchItem, WatchState
from ..schemas import ChannelOut, GameOut, JobRunOut, SettingsOut, StateOut, WatchItemOut
from ..services.settings_store import get_settings as load_settings
from ..timeutil import to_iso


def game_out(game: Game) -> GameOut:
    return GameOut(
        appid=game.appid,
        name=game.name,
        header_image=game.header_image,
        short_description=game.short_description or "",
        developers=game.developers or "",
        publishers=game.publishers or "",
        genres=game.genres or "",
        release_date=game.release_date or "",
        is_free=bool(game.is_free),
    )


def state_out(state: WatchState | None) -> StateOut | None:
    if state is None:
        return None
    return StateOut(
        cc=state.cc,
        currency=state.currency,
        current_initial_cents=state.current_initial_cents,
        current_final_cents=state.current_final_cents,
        current_discount_percent=state.current_discount_percent,
        available=bool(state.available),
        atl_cents=state.atl_cents,
        atl_first_at=to_iso(state.atl_first_at),
        atl_last_at=to_iso(state.atl_last_at),
        atl_hit_count=state.atl_hit_count or 0,
        first_change_at=to_iso(state.first_change_at),
        last_checked_at=to_iso(state.last_checked_at),
    )


def watch_item_out(session: Session, item: WatchItem) -> WatchItemOut:
    game = session.get(Game, item.appid)
    state = session.get(WatchState, item.appid)
    return WatchItemOut(
        appid=item.appid,
        name=game.name if game else "",
        header_image=game.header_image if game else "",
        cc=item.cc,
        note=item.note or "",
        sort_order=item.sort_order or 0,
        notify_enabled=bool(item.notify_enabled),
        target_price_cents=item.target_price_cents,
        discount_alert_threshold=item.discount_alert_threshold,
        created_at=to_iso(item.created_at) or "",
        currency=state.currency if state else "",
        current_initial_cents=state.current_initial_cents if state else 0,
        current_final_cents=state.current_final_cents if state else 0,
        current_discount_percent=state.current_discount_percent if state else 0,
        available=bool(state.available) if state else True,
        atl_cents=state.atl_cents if state else None,
        atl_hit_count=state.atl_hit_count if state else 0,
        atl_last_at=to_iso(state.atl_last_at) if state else None,
        last_checked_at=to_iso(state.last_checked_at) if state else None,
        record_started_at=to_iso(state.first_change_at) if state else None,
    )


def channels_out(session: Session) -> list[ChannelOut]:
    rows = session.execute(select(NotificationChannel).order_by(NotificationChannel.id)).scalars()
    out: list[ChannelOut] = []
    for row in rows:
        try:
            config = json.loads(row.config_json or "{}")
        except ValueError:
            config = {}
        out.append(ChannelOut(id=row.id, kind=row.kind, name=row.name, config=config, enabled=bool(row.enabled)))
    return out


def job_run_out(run: JobRun | None) -> JobRunOut | None:
    if run is None:
        return None
    return JobRunOut(
        id=run.id,
        job_type=run.job_type,
        status=run.status,
        started_at=to_iso(run.started_at),
        finished_at=to_iso(run.finished_at),
        checked_count=run.checked_count or 0,
        changed_count=run.changed_count or 0,
        error=run.error or "",
    )


def settings_out(session: Session) -> SettingsOut:
    stored = load_settings(session)
    return SettingsOut(
        poll_enabled=bool(stored["poll_enabled"]),
        poll_interval_hours=int(stored["poll_interval_hours"]),
        poll_time=str(stored["poll_time"]),
        cc=str(stored["cc"]),
        lang=str(stored["lang"]),
        steamid=str(stored["steamid"] or ""),
        proxy_url=str(stored["proxy_url"] or ""),
        wishlist_enabled=bool(stored["wishlist_enabled"]),
        wishlist_last_import_at=stored["wishlist_last_import_at"],
        next_poll_at=stored["next_poll_at"],
        meta_refresh_at=stored["meta_refresh_at"],
        channels=channels_out(session),
    )
