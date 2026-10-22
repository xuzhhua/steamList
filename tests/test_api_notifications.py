from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import NotificationLog
from app.services.steam_client import GameMeta, PriceResult
from app.timeutil import utcnow

APPD = 1245620
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


class FakeSteam:
    async def fetch_app(self, appid: int):
        return META, PRICE

    async def search(self, term: str, limit: int = 12):
        return []

    async def aclose(self) -> None:
        return None


@pytest.fixture()
def api(app):
    app.state.steam_factory = lambda cc, lang: FakeSteam()
    with TestClient(app) as test_client:
        yield test_client


def test_notification_log_lists_entries(api, app):
    api.post("/api/watchlist", json={"appid": APPD})
    with app.state.db.session() as session:
        session.add(
            NotificationLog(
                appid=APPD,
                rule="discount",
                dedupe_key="k1",
                title="《ELDEN RING》降价 50%",
                body="现价 ¥149.00",
                channel_id=None,
                status="sent",
                created_at=utcnow(),
                sent_at=utcnow(),
            )
        )
        session.commit()

    response = api.get("/api/notifications/log")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["game_name"] == "ELDEN RING"
    assert items[0]["rule"] == "discount"
    assert items[0]["sent_at"] is not None


def test_channel_test_endpoint(api, app):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"code": 200})

    app.state.notifier_transport = httpx.MockTransport(handler)
    settings = api.put(
        "/api/settings",
        json={"channels": [{"kind": "bark", "name": "phone", "config": {"url": "https://bark.example/key"}}]},
    ).json()
    channel_id = settings["channels"][0]["id"]

    response = api.post("/api/notifications/test", json={"channel_id": channel_id})
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert len(calls) == 1

    # missing channel id
    assert api.post("/api/notifications/test", json={"channel_id": 999}).status_code == 404


def test_channel_test_reports_failure(api, app):
    app.state.notifier_transport = httpx.MockTransport(
        lambda request: httpx.Response(500, json={"error": "boom"})
    )
    settings = api.put(
        "/api/settings",
        json={"channels": [{"kind": "webhook", "name": "hook", "config": {"url": "https://hooks.example/x"}}]},
    ).json()
    response = api.post(
        "/api/notifications/test", json={"channel_id": settings["channels"][0]["id"]}
    )
    results = response.json()["results"]
    assert results[0]["ok"] is False
    assert results[0]["error"]
