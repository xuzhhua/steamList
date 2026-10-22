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
        self.seen_input: str | None = None
        self.resolved = STEAMID
        self.profile = {
            "steamid": STEAMID,
            "persona": "TestUser",
            "privacy": "public",
            "visibility": "3",
        }
        self.visibility = "visible"

    async def resolve_steamid(self, value: str) -> str:
        self.seen_input = value
        return self.resolved

    async def fetch_wishlist(self, steamid: str):
        self.seen_steamid = steamid
        if self.error is not None:
            raise self.error
        return list(self.wishlist)

    async def fetch_profile(self, steamid: str):
        return self.profile

    async def wishlist_visibility(self, steamid: str) -> str:
        return self.visibility

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


def test_import_resolves_vanity_and_saves_canonical_steamid(api, fake):
    body = api.post("/api/watchlist/import", json={"steamid": "gaben"}).json()
    assert fake.seen_input == "gaben"
    assert fake.seen_steamid == STEAMID
    assert body["imported"] == 2
    assert api.get("/api/settings").json()["steamid"] == STEAMID


def test_import_explains_private_profile(api, fake):
    fake.wishlist = []
    fake.visibility = "hidden"
    fake.profile = {
        "steamid": STEAMID,
        "persona": "TestUser",
        "privacy": "private",
        "visibility": "1",
    }
    body = api.post("/api/watchlist/import", json={"steamid": STEAMID}).json()
    assert body["imported"] == 0
    assert body["errors"]
    assert "隐私" in body["errors"][0]
    assert "公开" in body["errors"][0]


def test_import_explains_empty_public_wishlist(api, fake):
    fake.wishlist = []
    fake.visibility = "visible"
    body = api.post("/api/watchlist/import", json={"steamid": STEAMID}).json()
    assert body["errors"]
    assert "没有游戏" in body["errors"][0]


def test_import_unknown_profile(api, fake):
    fake.wishlist = []
    fake.visibility = "unknown"
    fake.profile = None
    body = api.post("/api/watchlist/import", json={"steamid": STEAMID}).json()
    assert body["errors"]
    assert "找不到" in body["errors"][0]


class FakeAuth:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error: Exception | None = None

    async def access_token(self, refresh_token: str, steamid: str) -> str:
        self.calls.append((refresh_token, steamid))
        if self.error is not None:
            raise self.error
        return "access-token-1"


def _login(app, steamid: str = STEAMID, name: str = "TestUser") -> None:
    from app.services.settings_store import update_settings

    with app.state.db.session() as session:
        update_settings(
            session,
            {
                "steam_refresh_token": "refresh-1",
                "steamid": steamid,
                "steam_account_name": name,
            },
        )
        session.commit()


def test_import_uses_private_endpoint_when_logged_in(api, app, fake):
    from app.services.steam_auth import SteamAuthError  # noqa: F401 - documented behaviour

    auth = FakeAuth()
    app.state.steam_auth = auth
    _login(app)

    private_calls: list[tuple[str, str]] = []
    public_calls: list[str] = []

    async def fetch_wishlist_private(steamid: str, access_token: str):
        private_calls.append((steamid, access_token))
        return [APPD]

    async def fetch_wishlist(steamid: str):
        public_calls.append(steamid)
        return [APPD]

    fake.fetch_wishlist_private = fetch_wishlist_private
    fake.fetch_wishlist = fetch_wishlist

    body = api.post("/api/watchlist/import", json={}).json()
    assert body["imported"] == 1
    assert private_calls == [(STEAMID, "access-token-1")]
    assert public_calls == []
    assert auth.calls == [("refresh-1", STEAMID)]


def test_import_private_falls_back_to_public_for_other_account(api, app, fake):
    auth = FakeAuth()
    app.state.steam_auth = auth
    _login(app, steamid="76561197968052866", name="gaben")

    async def fetch_wishlist_private(steamid: str, access_token: str):  # pragma: no cover
        raise AssertionError("private endpoint must not be used for another account")

    fake.fetch_wishlist_private = fetch_wishlist_private
    fake.wishlist = []

    body = api.post("/api/watchlist/import", json={"steamid": STEAMID}).json()
    assert body["imported"] == 0
    assert any("不一致" in error for error in body["errors"])
    assert auth.calls == []


def test_import_private_relogin_required_returns_401(api, app, fake):
    from app.services.steam_auth import SteamAuthError

    auth = FakeAuth()
    auth.error = SteamAuthError("Steam 登录已失效，请在设置页重新扫码登录")
    app.state.steam_auth = auth
    _login(app)

    response = api.post("/api/watchlist/import", json={})
    assert response.status_code == 401
    assert "重新扫码" in response.json()["detail"]
