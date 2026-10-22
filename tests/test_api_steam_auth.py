from __future__ import annotations

import base64
import json

import httpx

from app.services.steam_auth import (
    ACCESS_TOKEN_URL,
    BEGIN_QR_URL,
    POLL_QR_URL,
    REVOKE_TOKEN_URL,
    SteamAuthService,
)

STEAMID = "76561197960287930"


def make_jwt(claims: dict) -> str:
    def encode(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'EdDSA', 'typ': 'JWT'})}.{encode(claims)}.signature"


ACCESS_TOKEN = make_jwt({"sub": STEAMID, "exp": 4102444800})


def install(app, poll_payload: dict, calls: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        url = str(request.url)
        if BEGIN_QR_URL in url:
            return httpx.Response(
                200,
                json={
                    "response": {
                        "client_id": "client-1",
                        "request_id": "request-1",
                        "challenge_url": "https://s.team/q/1/client-1",
                        "interval": 5,
                    }
                },
            )
        if POLL_QR_URL in url:
            return httpx.Response(200, json={"response": poll_payload})
        if ACCESS_TOKEN_URL in url:
            return httpx.Response(200, json={"response": {"access_token": ACCESS_TOKEN}})
        if REVOKE_TOKEN_URL in url:
            return httpx.Response(200, json={"response": {}})
        raise AssertionError(f"unexpected url {url}")

    app.state.steam_auth = SteamAuthService(app.state.settings, transport=httpx.MockTransport(handler))


def test_session_state_starts_disconnected(client):
    response = client.get("/api/steam/session")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "account_name": "", "steamid": "", "connected_at": None}


def test_qr_login_flow_persists_tokens(client, app):
    install(
        app,
        {"tokens": {"access_token": ACCESS_TOKEN, "refresh_token": "refresh-1"}, "account_name": "gaben"},
    )
    start = client.post("/api/steam/qr")
    assert start.status_code == 201
    body = start.json()
    assert body["challenge_url"] == "https://s.team/q/1/client-1"
    assert body["expires_in_seconds"] == 300

    poll = client.get(f"/api/steam/qr/{body['session_id']}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "success"
    assert poll.json()["account_name"] == "gaben"
    assert poll.json()["steamid"] == STEAMID

    state = client.get("/api/steam/session").json()
    assert state["connected"] is True
    assert state["account_name"] == "gaben"
    assert state["steamid"] == STEAMID
    assert state["connected_at"]


def test_qr_poll_pending(client, app):
    install(app, {})
    start = client.post("/api/steam/qr").json()
    poll = client.get(f"/api/steam/qr/{start['session_id']}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "pending"


def test_qr_poll_unknown_session_returns_404(client):
    assert client.get("/api/steam/qr/nope").status_code == 404


def test_qr_start_failure_returns_502(client, app):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    app.state.steam_auth = SteamAuthService(app.state.settings, transport=httpx.MockTransport(handler))
    response = client.post("/api/steam/qr")
    assert response.status_code == 502


def test_disconnect_revokes_and_clears(client, app):
    calls: list[httpx.Request] = []
    install(
        app,
        {"tokens": {"access_token": ACCESS_TOKEN, "refresh_token": "refresh-1"}, "account_name": "gaben"},
        calls,
    )
    start = client.post("/api/steam/qr").json()
    client.get(f"/api/steam/qr/{start['session_id']}")

    response = client.delete("/api/steam/session")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    settings = client.get("/api/settings").json()
    # The steamid is kept so public wishlist imports keep working after logout.
    assert settings["steamid"] == STEAMID
    assert client.get("/api/steam/session").json()["account_name"] == ""
    assert any(REVOKE_TOKEN_URL in str(request.url) for request in calls)


def test_refresh_token_is_not_exposed_by_settings(client, app):
    install(
        app,
        {"tokens": {"access_token": ACCESS_TOKEN, "refresh_token": "refresh-1"}, "account_name": "gaben"},
    )
    start = client.post("/api/steam/qr").json()
    client.get(f"/api/steam/qr/{start['session_id']}")
    payload = client.get("/api/settings").json()
    assert "steam_refresh_token" not in payload
    assert "refresh-1" not in json.dumps(payload)

