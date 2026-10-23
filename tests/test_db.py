from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import Game, PriceChange, WatchItem
from app.services.settings_store import DEFAULT_SETTINGS, get_settings, update_settings


def test_create_all_is_idempotent(db):
    db.create_all()
    db.create_all()


def test_default_settings(session):
    settings = get_settings(session)
    assert settings["cc"] == "cn"
    assert settings["poll_time"] == "03:30"
    assert settings["poll_interval_hours"] == 24
    assert settings["poll_enabled"] is True
    assert set(settings) == set(DEFAULT_SETTINGS)


def test_update_settings_roundtrip(session):
    update_settings(session, {"cc": "us", "poll_interval_hours": 6, "steamid": "76561197960287930"})
    session.commit()
    settings = get_settings(session)
    assert settings["cc"] == "us"
    assert settings["poll_interval_hours"] == 6
    assert settings["steamid"] == "76561197960287930"


def test_update_settings_rejects_unknown_key(session):
    with pytest.raises(ValueError):
        update_settings(session, {"nope": 1})


def test_watch_item_and_price_change(session):
    session.add(Game(appid=1245620, name="ELDEN RING"))
    session.add(WatchItem(appid=1245620, cc="cn", target_price_cents=19900))
    session.add(
        PriceChange(
            appid=1245620,
            cc="cn",
            currency="CNY",
            initial_cents=29800,
            final_cents=14900,
            discount_percent=50,
            available=True,
            changed_at=datetime(2026, 10, 22, 12, 0, 0),
        )
    )
    session.commit()

    item = session.execute(select(WatchItem)).scalar_one()
    assert item.target_price_cents == 19900
    assert item.notify_enabled is False
    assert session.execute(select(PriceChange)).scalar_one().final_cents == 14900


LEGACY_HEADER = (
    "https://cdn.akamai.steamstatic.com/steam/apps/2827750/"
    "d7d0e546e2ed7a1cd07f3abfdc2b65f140201b24/header.jpg?t=1792561823"
)
ASSET_HEADER = (
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/2827750/"
    "d7d0e546e2ed7a1cd07f3abfdc2b65f140201b24/header.jpg?t=1792561823"
)


def test_create_all_rewrites_legacy_cover_urls(tmp_path):
    from app.db import Database

    db_path = tmp_path / "migrate.db"
    first = Database(db_path)
    first.create_all()
    with first.session() as session:
        session.add(Game(appid=2827750, name="致命利爪", header_image=LEGACY_HEADER))
        session.commit()
    first.dispose()

    second = Database(db_path)
    second.create_all()
    with second.session() as session:
        game = session.get(Game, 2827750)
        assert game.header_image == ASSET_HEADER
    second.dispose()
