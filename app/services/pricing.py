"""Price ingestion: persist changes, maintain current state and ATL.

All money values are integer cents. Comparisons are strict so that a game
staying at the same price never creates duplicate history rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, PriceChange, WatchItem, WatchState
from ..timeutil import utcnow
from .steam_client import DEFAULT_CURRENCY, GameMeta, PriceResult


@dataclass
class PriceEvent:
    appid: int
    kind: str  # atl | target | discount
    final_cents: int
    previous_atl_cents: int | None
    discount_percent: int
    currency: str
    name: str = ""
    target_price_cents: int | None = None


@dataclass
class IngestResult:
    checked: int = 0
    changed: int = 0
    failed: list[int] = field(default_factory=list)
    events: list[PriceEvent] = field(default_factory=list)


def ensure_game(session: Session, meta: GameMeta, now: datetime | None = None) -> Game:
    game = session.get(Game, meta.appid)
    if game is None:
        game = Game(appid=meta.appid)
        session.add(game)
    if meta.name:
        game.name = meta.name
    if meta.header_image:
        game.header_image = meta.header_image
    if meta.short_description:
        game.short_description = meta.short_description
    if meta.developers:
        game.developers = meta.developers
    if meta.publishers:
        game.publishers = meta.publishers
    if meta.genres:
        game.genres = meta.genres
    if meta.release_date:
        game.release_date = meta.release_date
    if meta.is_free is not None:
        game.is_free = meta.is_free
    game.last_synced_at = now or utcnow()
    return game


def ensure_placeholder_game(session: Session, appid: int, name: str = "") -> Game:
    game = session.get(Game, appid)
    if game is None:
        game = Game(appid=appid, name=name)
        session.add(game)
        session.flush()
    elif name and not game.name:
        game.name = name
    return game


def ingest_prices(
    session: Session,
    results: dict[int, PriceResult | None],
    cc: str,
    now: datetime | None = None,
) -> IngestResult:
    """Apply one polling round's prices.

    * Only watched appids are considered.
    * History rows are inserted only when a field actually changes.
    * ATL counts every entry into a new or equal record low.
    * Events are returned for the notifier; nothing is committed here.
    """
    now = now or utcnow()
    outcome = IngestResult()
    if not results:
        return outcome

    items = {
        item.appid: item
        for item in session.execute(
            select(WatchItem).where(WatchItem.appid.in_(list(results)))
        ).scalars()
    }
    outcome.checked = len(items)

    for appid, item in items.items():
        price = results.get(appid)
        if price is None:
            outcome.failed.append(appid)
            continue

        state = session.get(WatchState, appid)
        currency = price.currency or DEFAULT_CURRENCY.get(cc, "")
        prev_final = state.current_final_cents if state is not None else None
        prev_initial = state.current_initial_cents if state is not None else None
        prev_discount = state.current_discount_percent if state is not None else None
        prev_available = state.available if state is not None else None
        prev_atl = state.atl_cents if state is not None else None

        changed = (
            state is None
            or price.final_cents != prev_final
            or price.initial_cents != prev_initial
            or price.discount_percent != prev_discount
            or price.available != prev_available
        )
        if changed:
            session.add(
                PriceChange(
                    appid=appid,
                    cc=cc,
                    currency=currency,
                    initial_cents=price.initial_cents,
                    final_cents=price.final_cents,
                    discount_percent=price.discount_percent,
                    available=price.available,
                    changed_at=now,
                )
            )
            outcome.changed += 1

        new_low = False
        if state is None:
            state = WatchState(appid=appid, cc=cc, currency=currency)
            session.add(state)
            state.first_change_at = now
        if price.available and price.final_cents > 0:
            if state.atl_cents is None:
                state.atl_cents = price.final_cents
                state.atl_first_at = now
                state.atl_last_at = now
                state.atl_hit_count = 1
            elif price.final_cents < state.atl_cents:
                state.atl_cents = price.final_cents
                state.atl_first_at = now
                state.atl_last_at = now
                state.atl_hit_count += 1
                new_low = True
            elif (
                price.final_cents == state.atl_cents
                and prev_final is not None
                and prev_final > state.atl_cents
            ):
                state.atl_hit_count += 1
                state.atl_last_at = now

        state.cc = cc
        state.currency = currency
        state.current_initial_cents = price.initial_cents
        state.current_final_cents = price.final_cents
        state.current_discount_percent = price.discount_percent
        state.available = price.available
        state.last_checked_at = now
        if state.first_change_at is None:
            state.first_change_at = now

        if not changed:
            continue

        game = session.get(Game, appid)
        game_name = game.name if game else ""

        if price.discount_percent > 0 and (
            prev_discount is None or prev_discount == 0 or price.discount_percent > prev_discount
        ):
            outcome.events.append(
                PriceEvent(
                    appid=appid,
                    kind="discount",
                    final_cents=price.final_cents,
                    previous_atl_cents=prev_atl,
                    discount_percent=price.discount_percent,
                    currency=currency,
                    name=game_name,
                )
            )
        if new_low and prev_atl is not None:
            outcome.events.append(
                PriceEvent(
                    appid=appid,
                    kind="atl",
                    final_cents=price.final_cents,
                    previous_atl_cents=prev_atl,
                    discount_percent=price.discount_percent,
                    currency=currency,
                    name=game_name,
                )
            )
        if (
            item.target_price_cents is not None
            and price.available
            and 0 < price.final_cents <= item.target_price_cents
            and (
                prev_final is None
                or prev_final > item.target_price_cents
                or (prev_discount or 0) == 0
            )
        ):
            outcome.events.append(
                PriceEvent(
                    appid=appid,
                    kind="target",
                    final_cents=price.final_cents,
                    previous_atl_cents=prev_atl,
                    discount_percent=price.discount_percent,
                    currency=currency,
                    name=game_name,
                    target_price_cents=item.target_price_cents,
                )
            )

    session.flush()
    return outcome
