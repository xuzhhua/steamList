from __future__ import annotations

import asyncio
import base64
import json
from datetime import timedelta

import httpx
import pytest

from app.services.steam_auth import (
    ACCESS_TOKEN_URL,
    BEGIN_QR_URL,
    POLL_QR_URL,
    REVOKE_TOKEN_URL,
    QRSession,
    SteamAuthError,
    SteamAuthService,
    decode_jwt_claims,
    token_steamid,
)
from app.timeutil import utcnow

STEAMID = "76561197960287930"


def make_jwt(claims: dict) -> str:
    def encode(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{encode({'alg': 'EdDSA', 'typ': 'JWT'})}.{encode(claims)}.signature"


ACCESS_TOKEN = make_jwt({"sub": STEAMID, "exp": 4102444800, "iss": "steam"})


def make_service(handler, settings) -> SteamAuthService:
    return SteamAuthService(settings, transport=httpx.MockTransport(handler))


def qr_handler(poll_payload: dict | None = None, calls: list[httpx.Request] | None = None):
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
            return httpx.Response(200, json={"response": poll_payload or {}})
        if ACCESS_TOKEN_URL in url:
            return httpx.Response(200, json={"response": {"access_token": ACCESS_TOKEN}})
        if REVOKE_TOKEN_URL in url:
            return httpx.Response(200, json={"response": {}})
        raise AssertionError(f"unexpected url {url}")

    return handler


def test_begin_qr_returns_session(settings):
    calls: list[httpx.Request] = []
    service = make_service(qr_handler(calls=calls), settings)

    session = asyncio.run(service.begin_qr())

    assert session.challenge_url == "https://s.team/q/1/client-1"
    assert session.interval == 5
    assert session.status == "pending"
    request = calls[0]
    assert BEGIN_QR_URL in str(request.url)
    payload = json.loads(request.url.params["input_json"])
    assert payload == {"device_friendly_name": "SteamList", "website_id": "Store"}


def test_begin_qr_rejects_incomplete_response(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"client_id": "x"}})

    service = make_service(handler, settings)
    with pytest.raises(SteamAuthError, match="二维码"):
        asyncio.run(service.begin_qr())


def test_poll_qr_success_stores_tokens(settings):
    service = make_service(
        qr_handler({"tokens": {"access_token": ACCESS_TOKEN, "refresh_token": "refresh-1"}, "account_name": "gaben"}),
        settings,
    )
    session = asyncio.run(service.begin_qr())
    polled = asyncio.run(service.poll_qr(session.session_id))

    assert polled.status == "success"
    assert polled.refresh_token == "refresh-1"
    assert polled.account_name == "gaben"
    assert polled.steamid == STEAMID


def test_poll_qr_scanned_when_user_interacted(settings):
    service = make_service(qr_handler({"had_remote_interaction": True}), settings)
    session = asyncio.run(service.begin_qr())
    assert asyncio.run(service.poll_qr(session.session_id)).status == "scanned"


def test_poll_qr_unknown_session_raises(settings):
    service = make_service(qr_handler({}), settings)
    with pytest.raises(SteamAuthError, match="会话"):
        asyncio.run(service.poll_qr("does-not-exist"))


def test_poll_qr_expires_after_ttl(settings):
    service = make_service(qr_handler({}), settings)
    session = asyncio.run(service.begin_qr())
    stale = session.created_at - timedelta(seconds=301)
    service._sessions[session.session_id] = QRSession(  # noqa: SLF001 - test seam
        session_id=session.session_id,
        client_id=session.client_id,
        request_id=session.request_id,
        challenge_url=session.challenge_url,
        interval=session.interval,
        created_at=stale,
    )
    polled = asyncio.run(service.poll_qr(session.session_id))
    assert polled.status == "expired"
    assert "重新生成" in (polled.error or "")


def test_access_token_is_cached(settings):
    calls: list[httpx.Request] = []
    service = make_service(qr_handler(calls=calls), settings)
    first = asyncio.run(service.access_token("refresh-1", STEAMID))
    second = asyncio.run(service.access_token("refresh-1", STEAMID))
    assert first == second == ACCESS_TOKEN
    assert sum(1 for request in calls if ACCESS_TOKEN_URL in str(request.url)) == 1


def test_access_token_empty_raises_relogin(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {}})

    service = make_service(handler, settings)
    with pytest.raises(SteamAuthError, match="重新扫码"):
        asyncio.run(service.access_token("stale-refresh", STEAMID))


def test_revoke_calls_steam(settings):
    calls: list[httpx.Request] = []
    service = make_service(qr_handler(calls=calls), settings)
    asyncio.run(service.revoke("refresh-1", STEAMID))
    assert any(REVOKE_TOKEN_URL in str(request.url) for request in calls)


def test_network_error_is_wrapped(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    service = make_service(handler, settings)
    with pytest.raises(SteamAuthError, match="无法连接"):
        asyncio.run(service.begin_qr())


def test_decode_jwt_claims_and_steamid():
    assert decode_jwt_claims(ACCESS_TOKEN)["sub"] == STEAMID
    assert token_steamid(ACCESS_TOKEN) == STEAMID


def test_decode_jwt_rejects_garbage():
    with pytest.raises(SteamAuthError):
        decode_jwt_claims("not-a-jwt")
    with pytest.raises(SteamAuthError):
        token_steamid(make_jwt({"exp": 1}))


def test_service_uses_proxy_when_configured(settings, monkeypatch):
    monkeypatch.setattr(settings, "proxy_url", "http://127.0.0.1:10808")
    service = SteamAuthService(settings)
    assert service._settings.proxy_url == "http://127.0.0.1:10808"  # noqa: SLF001
