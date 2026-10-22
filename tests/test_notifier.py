from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest

from app.models import NotificationChannel, NotificationLog
from app.services.notifier import Notifier, build_message, format_price
from app.services.pricing import PriceEvent
from app.timeutil import utcnow

APPD = 1245620
NOW = utcnow()


def make_channel(session, kind="bark", config=None, enabled=True, name=None):
    channel = NotificationChannel(
        kind=kind,
        name=name or kind,
        config_json=json.dumps(config or {}),
        enabled=enabled,
    )
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


def make_event(kind="discount", **overrides):
    payload = dict(
        appid=APPD,
        kind=kind,
        final_cents=14900,
        previous_atl_cents=None,
        discount_percent=50,
        currency="CNY",
        name="ELDEN RING",
    )
    payload.update(overrides)
    return PriceEvent(**payload)


def recording_transport(calls, status=200, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body or {"code": 200})

    return httpx.MockTransport(handler)


def test_bark_delivery(session):
    make_channel(session, "bark", {"url": "https://bark.example/key", "sound": "bell"})
    calls: list[httpx.Request] = []
    result = Notifier(session, transport=recording_transport(calls)).notify([make_event()], NOW)

    assert result.sent == 1
    assert result.failed == 0
    assert len(calls) == 1
    assert str(calls[0].url) == "https://bark.example/key"
    payload = json.loads(calls[0].content)
    assert payload["title"].startswith("《ELDEN RING》降价")
    assert "¥149.00" in payload["body"]
    assert payload["sound"] == "bell"

    log = session.query(NotificationLog).one()
    assert log.status == "sent"
    assert log.rule == "discount"
    assert log.sent_at is not None


def test_duplicate_notification_is_skipped(session):
    make_channel(session, "bark", {"url": "https://bark.example/key"})
    calls: list[httpx.Request] = []
    notifier = Notifier(session, transport=recording_transport(calls))
    event = make_event()
    first = notifier.notify([event], NOW)
    second = notifier.notify([event], NOW)

    assert first.sent == 1
    assert second.sent == 0
    assert second.skipped == 1
    assert len(calls) == 1
    assert session.query(NotificationLog).count() == 1

    # the next day is a new dedupe window
    third = notifier.notify([event], NOW + timedelta(days=1))
    assert third.sent == 1


def test_webhook_payload(session):
    make_channel(
        session,
        "webhook",
        {"url": "https://hooks.example/steam", "method": "put", "headers": {"X-Token": "secret"}},
    )
    calls: list[httpx.Request] = []
    event = make_event(kind="atl", previous_atl_cents=19900)
    Notifier(session, transport=recording_transport(calls)).notify([event], NOW)

    request = calls[0]
    assert request.method == "PUT"
    assert request.headers["x-token"] == "secret"
    payload = json.loads(request.content)
    assert payload["appid"] == APPD
    assert payload["rule"] == "atl"
    assert payload["final_cents"] == 14900
    assert payload["occurred_at"].endswith("Z")


def test_failed_delivery_is_logged(session):
    make_channel(session, "bark", {"url": "https://bark.example/key"})
    calls: list[httpx.Request] = []
    result = Notifier(session, transport=recording_transport(calls, status=500)).notify([make_event()], NOW)

    assert result.failed == 1
    log = session.query(NotificationLog).one()
    assert log.status == "error"
    assert log.error


def test_disabled_channel_is_ignored(session):
    make_channel(session, "bark", {"url": "https://bark.example/key"}, enabled=False)
    result = Notifier(session).notify([make_event()], NOW)
    assert result.skipped == 1
    assert session.query(NotificationLog).count() == 0


def test_email_channel_without_config_fails(session):
    make_channel(session, "email", {"host": "smtp.example"})
    result = Notifier(session).notify([make_event()], NOW)
    assert result.failed == 1
    log = session.query(NotificationLog).one()
    assert "email" in log.error
    assert log.status == "error"


def test_format_price():
    assert format_price(14900, "CNY") == "¥149.00"
    assert format_price(2999, "USD") == "$29.99"
    assert format_price(100, "XYZ") == "XYZ 1.00"
    assert format_price(None, "CNY") == "-"


def test_build_message_variants():
    atl_title, atl_body = build_message(make_event(kind="atl", previous_atl_cents=19900))
    assert "历史低价" in atl_title
    assert "¥199.00" in atl_body

    target_title, target_body = build_message(make_event(kind="target", target_price_cents=15000))
    assert "目标价" in target_title
    assert "¥150.00" in target_body


def test_send_test(session):
    channel = make_channel(session, "bark", {"url": "https://bark.example/key"})
    calls: list[httpx.Request] = []
    ok, error = Notifier(session, transport=recording_transport(calls)).send_test(channel)
    assert ok is True
    assert error == ""
    assert json.loads(calls[0].content)["title"] == "SteamList 测试通知"

    broken = make_channel(session, "bark", {})
    ok, error = Notifier(session).send_test(broken)
    assert ok is False
    assert "url" in error
