from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.services.pricing import ingest_prices
from app.services.steam_client import GameMeta, PriceResult, SearchItem, SteamError
from app.timeutil import utcnow

APPD = 1245620
META = GameMeta(
    appid=APPD,
    name="ELDEN RING",
    header_image="https://cdn.example/header.jpg",
    short_description="Rise, Tarnished.",
    developers="FromSoftware, Inc.",
    publishers="FromSoftware, Inc.",
    genres="Action, RPG",
    release_date="24 Feb, 2022",
    is_free=False,
)
PRICE_HALF = PriceResult(
    appid=APPD,
    currency="CNY",
    initial_cents=29800,
    final_cents=14900,
    discount_percent=50,
    available=True,
    is_free=False,
)
PRICE_FULL = PriceResult(
    appid=APPD,
    currency="CNY",
    initial_cents=29800,
    final_cents=29800,
    discount_percent=0,
    available=True,
    is_free=False,
)


class FakeSteam:
    def __init__(self) -> None:
        self.meta = META
        self.price = PRICE_HALF
        self.error: Exception | None = None
        self.search_items: list[SearchItem] = []
        self.calls: list[tuple] = []

    async def fetch_app(self, appid: int):
        self.calls.append(("fetch_app", appid))
        if self.error is not None:
            raise self.error
        return self.meta, self.price

    async def search(self, term: str, limit: int = 12):
        self.calls.append(("search", term, limit))
        if self.error is not None:
            raise self.error
        return self.search_items

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def fake(app):
    client = FakeSteam()
    app.state.steam_factory = lambda cc, lang: client
    return client


@pytest.fixture()
def api(app, fake):
    with TestClient(app) as test_client:
        yield test_client


def add(api, **payload):
    body = {"appid": APPD}
    body.update(payload)
    return api.post("/api/watchlist", json=body)


def test_add_returns_game_and_state(api):
    response = add(api, notify_enabled=True)
    assert response.status_code == 201
    item = response.json()
    assert item["appid"] == APPD
    assert item["name"] == "ELDEN RING"
    assert item["notify_enabled"] is True
    assert item["currency"] == "CNY"
    assert item["current_final_cents"] == 14900
    assert item["current_discount_percent"] == 50
    assert item["atl_cents"] == 14900
    assert item["atl_hit_count"] == 1
    assert item["record_started_at"] is not None


def test_duplicate_add_is_idempotent(api):
    assert add(api).status_code == 201
    again = add(api)
    assert again.status_code == 200
    listing = api.get("/api/watchlist").json()
    assert listing["summary"]["count"] == 1
    assert len(listing["items"]) == 1


def test_list_summary_counts_targets(api):
    add(api, target_price_cents=15000)
    listing = api.get("/api/watchlist").json()
    summary = listing["summary"]
    assert summary["count"] == 1
    assert summary["discounting_count"] == 1
    assert summary["atl_count"] == 1
    assert summary["below_target_count"] == 1
    assert summary["last_checked_at"] is not None


def test_patch_updates_and_clears_fields(api):
    add(api)
    patched = api.patch(
        f"/api/watchlist/{APPD}",
        json={"target_price_cents": 10000, "note": "wait for 50%", "notify_enabled": True},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["target_price_cents"] == 10000
    assert body["note"] == "wait for 50%"
    assert body["notify_enabled"] is True

    cleared = api.patch(f"/api/watchlist/{APPD}", json={"target_price_cents": None})
    assert cleared.status_code == 200
    assert cleared.json()["target_price_cents"] is None


def test_patch_missing_item_returns_404(api):
    assert api.patch(f"/api/watchlist/{APPD}", json={"note": "x"}).status_code == 404


def test_delete_removes_watchlist_item_but_keeps_history(api, app):
    add(api)
    deleted = api.delete(f"/api/watchlist/{APPD}")
    assert deleted.status_code == 204
    assert api.get("/api/watchlist").json()["summary"]["count"] == 0

    from app.models import PriceChange

    with app.state.db.session() as session:
        count = session.query(PriceChange).filter(PriceChange.appid == APPD).count()
    assert count == 1

    # re-adding after removal works (no stale 409)
    assert add(api).status_code == 201


def test_add_survives_steam_failure(api, fake):
    fake.error = SteamError("network down")
    response = add(api)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == ""
    assert body["current_final_cents"] == 0


def test_search_endpoint(api, fake):
    assert api.get("/api/games/search", params={"term": "e"}).status_code == 400
    fake.search_items = [
        SearchItem(
            appid=APPD,
            name="ELDEN RING",
            header_image="https://cdn.example/header.jpg",
            price_cents=29800,
            currency="CNY",
        )
    ]
    response = api.get("/api/games/search", params={"term": "elden"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["appid"] == APPD
    assert items[0]["price_cents"] == 29800


def test_search_failure_returns_502(api, fake):
    fake.error = SteamError("boom")
    assert api.get("/api/games/search", params={"term": "elden"}).status_code == 502


def test_game_detail_requires_watchlist(api):
    assert api.get(f"/api/games/{APPD}").status_code == 404
    add(api)
    detail = api.get(f"/api/games/{APPD}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["game"]["name"] == "ELDEN RING"
    assert payload["watch"]["appid"] == APPD


def test_series_builds_step_points_and_anchor(api, app):
    add(api)
    with app.state.db.session() as session:
        later = utcnow() + timedelta(days=1)
        ingest_prices(session, {APPD: PRICE_FULL}, "cn", now=later)
        session.commit()

    response = api.get(f"/api/games/{APPD}/series", params={"range": "all"})
    assert response.status_code == 200
    payload = response.json()
    points = payload["points"]
    assert [p["final"] for p in points] == [14900, 29800]
    assert payload["record_started_at"] is not None
    assert payload["currency"] == "CNY"

    last_30 = api.get(f"/api/games/{APPD}/series", params={"range": "30d"}).json()
    assert last_30["points"][0]["t"] < last_30["end"]


def test_series_rejects_unknown_range(api):
    add(api)
    assert api.get(f"/api/games/{APPD}/series", params={"range": "42d"}).status_code == 400


def test_series_and_stats_require_watchlist(api):
    assert api.get(f"/api/games/{APPD}/series").status_code == 404
    assert api.get(f"/api/games/{APPD}/stats").status_code == 404


def test_stats_endpoint(api, app):
    add(api)
    with app.state.db.session() as session:
        later = utcnow() + timedelta(days=2)
        ingest_prices(session, {APPD: PRICE_FULL}, "cn", now=later)
        session.commit()

    response = api.get(f"/api/games/{APPD}/stats")
    assert response.status_code == 200
    payload = response.json()
    stats = payload["stats"]
    assert stats["atl_cents"] == 14900
    assert stats["atl_hit_count"] == 1
    assert stats["discount_event_count"] == 1
    assert stats["max_discount_percent"] == 50
    assert payload["record_started_at"] is not None


def test_settings_roundtrip(api):
    initial = api.get("/api/settings")
    assert initial.status_code == 200
    body = initial.json()
    assert body["cc"] == "cn"
    assert body["poll_time"] == "03:30"
    assert body["channels"] == []

    updated = api.put(
        "/api/settings",
        json={
            "poll_time": "04:15",
            "target": "ignored",
            "channels": [
                {"kind": "bark", "name": "iPhone", "config": {"url": "https://bark.example/key"}, "enabled": True}
            ],
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["poll_time"] == "04:15"
    assert len(body["channels"]) == 1
    channel = body["channels"][0]
    assert channel["kind"] == "bark"
    assert channel["config"]["url"] == "https://bark.example/key"
    assert channel["id"] > 0

    cleared = api.put("/api/settings", json={"channels": []}).json()
    assert cleared["channels"] == []


def test_settings_validation(api):
    assert api.put("/api/settings", json={"poll_time": "25:00"}).status_code == 422
    assert api.put("/api/settings", json={"poll_interval_hours": 0}).status_code == 422
