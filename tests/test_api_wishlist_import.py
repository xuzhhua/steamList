from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.steam_client import GameMeta, PriceResult, SteamError

APPD = 1245620
OTHER = 999
META = GameMeta(
    appid=APPD,
    name="ELDEN RING",
    header_image="https://cdn.example/header.jpg",
    short_description="",
    developers="FromSoftware",
    publishers="FromSoftware",
    genres="Action, RPG",
    release_date="24 Feb, 2022",
    is_free=False,
)
PRICE = PriceResult(
    appid=APPD,
    currency="CNY",
    initial_cents=29800,
    final_cents=14900,
    discount_percent=50,
    available=True,
    is_free=False,
)
STEAMID = "76561197960287930"


class FakeWishlistSteam:
    def __init__(self) -> None:
        self.wishlist = [APPD, OTHER]
        self.prices = {APPD: PRICE}
        self.metas = {APPD: META}
        self.error: Exception | None = None
        self.seen_steamid: str | None = None

    async def fetch_wishlist(self, steamid: str):
        self.seen_steamid = steamid
        if self.error is not None:
            raise self.error
        return list(self.wishlist)

    async def fetch_prices(self, appids):
        return {appid: self.prices.get(appid) for appid in appids}

    async def fetch_metas(self, appids):
        return {appid: self.metas[appid] for appid in appids if appid in self.metas}

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def fake(app):
    client = FakeWishlistSteam()
    app.state.steam_factory = lambda cc, lang: client
    return client


@pytest.fixture()
def api(app, fake):
    with TestClient(app) as test_client:
        yield test_client


def test_import_wishlist(api, app, fake):
    response = api.post("/api/watchlist/import", json={"steamid": STEAMID})
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert body["failed"] == 1  # OTHER has no price data
    assert body["total"] == 2
    assert body["appids"] == [APPD, OTHER]
    assert fake.seen_steamid == STEAMID

    listing = api.get("/api/watchlist").json()
    assert listing["summary"]["count"] == 2
    el = next(i for i in listing["items"] if i["appid"] == APPD)
    assert el["name"] == "ELDEN RING"
    assert el["current_final_cents"] == 14900

    settings = api.get("/api/settings").json()
    assert settings["wishlist_last_import_at"] is not None

    again = api.post("/api/watchlist/import", json={"steamid": STEAMID}).json()
    assert again["imported"] == 0
    assert again["skipped"] == 2


def test_import_uses_saved_steamid(api, fake):
    api.put("/api/settings", json={"steamid": STEAMID})
    assert api.post("/api/watchlist/import", json={}).status_code == 200
    assert fake.seen_steamid == STEAMID


def test_import_requires_steamid(api):
    response = api.post("/api/watchlist/import", json={})
    assert response.status_code == 400
    assert "steamid" in response.json()["detail"]


def test_import_empty_wishlist(api, fake):
    fake.wishlist = []
    response = api.post("/api/watchlist/import", json={"steamid": STEAMID})
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 0
    assert body["errors"]


def test_import_steam_failure(api, fake):
    fake.error = SteamError("profile private")
    response = api.post("/api/watchlist/import", json={"steamid": STEAMID})
    assert response.status_code == 502
    assert "profile private" in response.json()["detail"]


def test_import_respects_limit(api, fake):
    fake.wishlist = [APPD, OTHER]
    body = api.post("/api/watchlist/import", json={"steamid": STEAMID, "limit": 1}).json()
    assert body["total"] == 1
    assert body["appids"] == [APPD]
