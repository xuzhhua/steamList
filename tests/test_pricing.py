from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Game, PriceChange, WatchItem, WatchState
from app.services.pricing import ensure_game, ingest_prices
from app.services.steam_client import GameMeta, PriceResult

T0 = datetime(2026, 10, 22, 3, 30, 0)


def pr(appid: int, final: int, *, initial: int | None = None, discount: int = 0,
       available: bool = True, is_free: bool = False) -> PriceResult:
    return PriceResult(
        appid=appid,
        currency="CNY",
        initial_cents=initial if initial is not None else final,
        final_cents=final,
        discount_percent=discount,
        available=available,
        is_free=is_free,
    )


def add_watch(session, appid: int = 1245620, target: int | None = None):
    session.add(Game(appid=appid, name="ELDEN RING"))
    session.flush()
    session.add(WatchItem(appid=appid, cc="cn", target_price_cents=target))
    session.flush()


def test_first_snapshot_sets_atl(session):
    add_watch(session)
    result = ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    assert result.checked == 1
    assert result.changed == 1
    state = session.get(WatchState, 1245620)
    assert state.atl_cents == 29800
    assert state.atl_hit_count == 1
    assert state.first_change_at == T0
    assert state.last_checked_at == T0
    assert session.execute(select(PriceChange)).scalars().all()[0].final_cents == 29800


def test_unchanged_price_is_not_duplicated(session):
    add_watch(session)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    result = ingest_prices(
        session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0 + timedelta(hours=1)
    )
    assert result.changed == 0
    assert len(session.execute(select(PriceChange)).scalars().all()) == 1
    assert session.get(WatchState, 1245620).last_checked_at == T0 + timedelta(hours=1)


def test_new_low_increments_hits_and_emits_events(session):
    add_watch(session)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    result = ingest_prices(
        session,
        {1245620: pr(1245620, 14900, initial=29800, discount=50)},
        cc="cn",
        now=T0 + timedelta(days=5),
    )
    state = session.get(WatchState, 1245620)
    assert state.atl_cents == 14900
    assert state.atl_hit_count == 2
    assert [event.kind for event in result.events] == ["discount", "atl"]
    assert result.events[1].previous_atl_cents == 29800


def test_rise_back_does_not_change_atl(session):
    add_watch(session)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    ingest_prices(session, {1245620: pr(1245620, 14900, discount=50)}, cc="cn", now=T0 + timedelta(days=1))
    result = ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0 + timedelta(days=2))
    state = session.get(WatchState, 1245620)
    assert state.atl_cents == 14900
    assert state.atl_hit_count == 2
    assert result.changed == 1
    assert result.events == []


def test_returning_to_atl_counts_another_hit(session):
    add_watch(session)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    ingest_prices(session, {1245620: pr(1245620, 14900, discount=50)}, cc="cn", now=T0 + timedelta(days=1))
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0 + timedelta(days=2))
    ingest_prices(session, {1245620: pr(1245620, 14900, discount=50)}, cc="cn", now=T0 + timedelta(days=3))
    assert session.get(WatchState, 1245620).atl_hit_count == 3


def test_unavailable_game_is_not_treated_as_zero_price(session):
    add_watch(session)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    result = ingest_prices(
        session,
        {1245620: pr(1245620, 0, available=False)},
        cc="cn",
        now=T0 + timedelta(days=1),
    )
    state = session.get(WatchState, 1245620)
    assert result.changed == 1
    assert state.available is False
    assert state.atl_cents == 29800
    assert state.atl_hit_count == 1


def test_free_game_has_no_atl(session):
    add_watch(session, appid=730)
    result = ingest_prices(session, {730: pr(730, 0, is_free=True)}, cc="cn", now=T0)
    state = session.get(WatchState, 730)
    assert result.changed == 1
    assert state.available is True
    assert state.atl_cents is None
    assert result.events == []


def test_target_event_when_price_crosses_target(session):
    add_watch(session, target=15000)
    ingest_prices(session, {1245620: pr(1245620, 29800)}, cc="cn", now=T0)
    result = ingest_prices(
        session,
        {1245620: pr(1245620, 14900, discount=50)},
        cc="cn",
        now=T0 + timedelta(days=1),
    )
    kinds = [event.kind for event in result.events]
    assert "target" in kinds
    target_event = next(e for e in result.events if e.kind == "target")
    assert target_event.target_price_cents == 15000
    assert target_event.final_cents == 14900


def test_unwatched_appid_is_ignored(session):
    add_watch(session)
    result = ingest_prices(session, {999: pr(999, 1000)}, cc="cn", now=T0)
    assert result.checked == 0
    assert result.changed == 0
    assert session.execute(select(PriceChange)).scalars().all() == []


def test_failed_fetch_is_reported(session):
    add_watch(session)
    result = ingest_prices(session, {1245620: None}, cc="cn", now=T0)
    assert result.checked == 1
    assert result.failed == [1245620]
    assert result.changed == 0


def test_ensure_game_upserts(session):
    meta = GameMeta(
        appid=1245620,
        name="ELDEN RING",
        header_image="https://cdn.example/header.jpg",
        short_description="desc",
        developers="FromSoftware, Inc.",
        publishers="Bandai Namco",
        genres="Action, RPG",
        release_date="24 Feb, 2022",
        is_free=False,
    )
    game = ensure_game(session, meta, now=T0)
    assert game.name == "ELDEN RING"
    assert game.last_synced_at == T0
    game2 = ensure_game(session, meta, now=T0 + timedelta(days=1))
    assert game2.appid == 1245620
    assert game2.last_synced_at == T0 + timedelta(days=1)
