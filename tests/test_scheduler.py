from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import Game, JobRun, NotificationLog
from app.services.pricing import PriceEvent
from app.services.scheduler import PollBusy, compute_next_poll
from app.services.settings_store import update_settings
from app.services.steam_client import GameMeta, PriceResult, SteamError
from app.timeutil import to_iso, utcnow

APPD = 1245620
META = GameMeta(
    appid=APPD,
    name="ELDEN RING",
    header_image="https://cdn.example/header.jpg",
    short_description="Rise, Tarnished.",
    developers="FromSoftware",
    publishers="FromSoftware",
    genres="Action, RPG",
    release_date="24 Feb, 2022",
    is_free=False,
)


def price(final: int, discount: int = 0) -> PriceResult:
    return PriceResult(
        appid=APPD,
        currency="CNY",
        initial_cents=29800,
        final_cents=final,
        discount_percent=discount,
        available=True,
        is_free=False,
    )


class FakePollClient:
    def __init__(self) -> None:
        self.prices: dict[int, PriceResult | None] = {APPD: price(14900, 50)}
        self.metas: dict[int, GameMeta] = {APPD: META}
        self.error: Exception | None = None
        self.price_calls = 0
        self.meta_calls = 0

    async def fetch_app(self, appid: int):
        return META, self.prices.get(appid)

    async def fetch_prices(self, appids):
        self.price_calls += 1
        if self.error is not None:
            raise self.error
        return {appid: self.prices.get(appid) for appid in appids}

    async def fetch_metas(self, appids):
        self.meta_calls += 1
        if self.error is not None:
            raise self.error
        return {appid: self.metas[appid] for appid in appids if appid in self.metas}

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def fake(app):
    client = FakePollClient()
    app.state.steam_factory = lambda cc, lang: client
    app.state.poller.client_factory = lambda cc, lang: client
    return client


@pytest.fixture()
def api(app, fake):
    with TestClient(app) as test_client:
        yield test_client


def add(api, **payload):
    body = {"appid": APPD}
    body.update(payload)
    return api.post("/api/watchlist", json=body)


# -- schedule maths ---------------------------------------------------------

def test_compute_next_poll_same_day():
    now = datetime(2026, 10, 21, 19, 0)  # 03:00 Asia/Shanghai
    settings = {"poll_enabled": True, "poll_interval_hours": 24, "poll_time": "03:30"}
    assert compute_next_poll(settings, now, "Asia/Shanghai") == "2026-10-21T19:30:00Z"


def test_compute_next_poll_next_day():
    now = datetime(2026, 10, 21, 20, 0)  # 04:00 Asia/Shanghai
    settings = {"poll_enabled": True, "poll_interval_hours": 24, "poll_time": "03:30"}
    assert compute_next_poll(settings, now, "Asia/Shanghai") == "2026-10-22T19:30:00Z"


def test_compute_next_poll_disabled_and_interval():
    assert compute_next_poll({"poll_enabled": False}) is None
    now = datetime(2026, 10, 21, 12, 0)
    settings = {"poll_enabled": True, "poll_interval_hours": 6, "poll_time": "03:30"}
    assert compute_next_poll(settings, now, "Asia/Shanghai") == "2026-10-21T18:00:00Z"


# -- poll runs --------------------------------------------------------------

def test_poll_records_history_and_meta_once(api, app, fake):
    add(api)
    poller = app.state.poller
    first = poller.run_poll(now=utcnow() + timedelta(hours=1))
    assert first > 0
    assert fake.meta_calls == 1

    fake.prices[APPD] = price(29800, 0)
    second = poller.run_poll(now=utcnow() + timedelta(days=1))
    assert second == first + 1
    assert fake.meta_calls == 1  # metadata refreshed at most weekly

    series = api.get(f"/api/games/{APPD}/series").json()
    assert [p["final"] for p in series["points"]] == [14900, 29800]

    status = api.get("/api/jobs/status").json()
    assert status["running"] is False
    assert status["last"]["id"] == second
    assert status["last"]["status"] == "success"
    assert status["last"]["checked_count"] == 1
    assert status["last"]["changed_count"] == 1
    assert status["next_poll_at"] is not None


def test_poll_dispatches_notifications(api, app, fake):
    add(api)
    channel = api.put(
        "/api/settings",
        json={
            "channels": [
                {"kind": "bark", "name": "phone", "config": {"url": "https://bark.example/key"}, "enabled": True}
            ]
        },
    )
    assert channel.status_code == 200

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200})

    app.state.poller.notifier_transport = httpx.MockTransport(handler)
    fake.prices[APPD] = price(9900, 67)
    app.state.poller.run_poll(now=utcnow() + timedelta(days=1))

    assert len(requests) == 2  # deeper discount + fresh all-time low
    with app.state.db.session() as session:
        logs = session.query(NotificationLog).all()
    assert len(logs) == 2
    assert {log.rule for log in logs} == {"atl", "discount"}
    assert all(log.status == "sent" for log in logs)


def test_poll_failure_is_recorded(api, app, fake):
    add(api)
    fake.error = SteamError("steam down")
    with pytest.raises(SteamError):
        app.state.poller.run_poll(now=utcnow())
    assert app.state.poller.running is False

    with app.state.db.session() as session:
        run = session.query(JobRun).order_by(JobRun.id.desc()).first()
    assert run.status == "error"
    assert "steam down" in run.error


def test_poll_busy_guard(app):
    poller = app.state.poller
    poller._running = True
    try:
        with pytest.raises(PollBusy):
            poller.run_poll(now=utcnow())
    finally:
        poller._running = False


def test_manual_refresh_endpoint(api, app, fake):
    add(api)
    response = api.post("/api/jobs/refresh")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "started"
    assert body["job_id"] > 0

    poller = app.state.poller
    assert poller._thread is not None
    poller._thread.join(timeout=10)
    assert poller.running is False

    status = api.get("/api/jobs/status").json()
    assert status["last"]["id"] == body["job_id"]
    assert status["last"]["status"] == "success"


def test_manual_refresh_conflict(api, app):
    poller = app.state.poller
    poller._running = True
    try:
        assert api.post("/api/jobs/refresh").status_code == 409
    finally:
        poller._running = False


def test_poll_backfills_missing_metadata_without_waiting_a_week(api, app, fake):
    add(api)
    with app.state.db.session() as session:
        game = session.get(Game, APPD)
        game.name = ""
        game.header_image = ""
        game.short_description = ""
        update_settings(session, {"meta_refresh_at": to_iso(utcnow())})
        session.commit()

    fake.meta_calls = 0
    app.state.poller.run_poll(now=utcnow() + timedelta(hours=1))
    assert fake.meta_calls == 1

    with app.state.db.session() as session:
        game = session.get(Game, APPD)
        assert game.name == META.name
        assert game.header_image == META.header_image
        assert game.short_description == META.short_description


def test_poll_skips_metadata_when_nothing_missing(api, app, fake):
    add(api)
    with app.state.db.session() as session:
        update_settings(session, {"meta_refresh_at": to_iso(utcnow())})
        session.commit()

    fake.meta_calls = 0
    app.state.poller.run_poll(now=utcnow() + timedelta(hours=1))
    assert fake.meta_calls == 0
