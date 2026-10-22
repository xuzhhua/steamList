"""Outbound notification delivery (Bark, e-mail, generic webhook)."""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NotificationChannel, NotificationLog
from ..timeutil import to_iso, utcnow
from .pricing import PriceEvent

logger = logging.getLogger(__name__)

CURRENCY_SYMBOLS = {
    "CNY": "¥",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "KRW": "₩",
    "RUB": "₽",
    "BRL": "R$",
    "TRY": "₺",
    "INR": "₹",
}

WEBHOOK_METHODS = {"POST", "PUT", "PATCH"}


def format_price(cents: int | None, currency: str) -> str:
    if cents is None:
        return "-"
    symbol = CURRENCY_SYMBOLS.get(currency.upper())
    amount = f"{cents / 100:.2f}"
    if symbol:
        return f"{symbol}{amount}"
    return f"{currency.upper()} {amount}"


def build_message(event: PriceEvent) -> tuple[str, str]:
    name = event.name or f"AppID {event.appid}"
    price = format_price(event.final_cents, event.currency)
    if event.kind == "atl":
        title = f"《{name}》刷新历史低价 {price}"
        body = f"当前价格 {price}，折扣 {event.discount_percent}%。"
        if event.previous_atl_cents is not None:
            body += f"\n原历史低价 {format_price(event.previous_atl_cents, event.currency)}。"
    elif event.kind == "target":
        title = f"《{name}》达到目标价 {price}"
        body = f"当前价格 {price}，目标价 {format_price(event.target_price_cents, event.currency)}。"
    else:
        title = f"《{name}》降价 {event.discount_percent}%"
        body = f"当前价格 {price}，折扣 {event.discount_percent}%。"
    return title, body


def dedupe_key(event: PriceEvent, channel_id: int, now: datetime) -> str:
    return f"{event.appid}:{event.kind}:{event.final_cents}:{channel_id}:{now.date().isoformat()}"


@dataclass
class NotificationResult:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class Notifier:
    def __init__(self, session: Session, *, transport: httpx.BaseTransport | None = None, timeout: float = 15.0):
        self.session = session
        self.transport = transport
        self.timeout = timeout

    def channels(self) -> list[NotificationChannel]:
        return list(
            self.session.execute(
                select(NotificationChannel)
                .where(NotificationChannel.enabled.is_(True))
                .order_by(NotificationChannel.id)
            ).scalars()
        )

    def notify(self, events: list[PriceEvent], now: datetime | None = None) -> NotificationResult:
        now = now or utcnow()
        result = NotificationResult()
        channels = self.channels()
        if not events:
            return result
        if not channels:
            result.skipped += len(events)
            return result

        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            for event in events:
                title, body = build_message(event)
                for channel in channels:
                    key = dedupe_key(event, channel.id, now)
                    exists = self.session.execute(
                        select(NotificationLog.id).where(NotificationLog.dedupe_key == key)
                    ).first()
                    if exists:
                        result.skipped += 1
                        continue
                    log = NotificationLog(
                        appid=event.appid,
                        rule=event.kind,
                        dedupe_key=key,
                        title=title,
                        body=body,
                        channel_id=channel.id,
                        status="pending",
                        created_at=now,
                    )
                    self.session.add(log)
                    self.session.flush()
                    try:
                        self._send(client, channel, title, body, event)
                    except Exception as exc:  # noqa: BLE001 - a bad channel must not break polling
                        log.status = "error"
                        log.error = str(exc)[:500]
                        result.failed += 1
                        logger.warning("notification via %s failed: %s", channel.kind, exc)
                    else:
                        log.status = "sent"
                        log.sent_at = utcnow()
                        result.sent += 1
        self.session.flush()
        return result

    def send_test(self, channel: NotificationChannel) -> tuple[bool, str]:
        title = "SteamList 测试通知"
        body = "如果你收到这条消息，说明通知渠道配置正确。"
        event = PriceEvent(
            appid=0,
            kind="test",
            final_cents=0,
            previous_atl_cents=None,
            discount_percent=0,
            currency="CNY",
        )
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                self._send(client, channel, title, body, event)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)[:500]
        return True, ""

    def _send(
        self,
        client: httpx.Client,
        channel: NotificationChannel,
        title: str,
        body: str,
        event: PriceEvent,
    ) -> None:
        config = json.loads(channel.config_json or "{}")
        if channel.kind == "bark":
            self._send_bark(client, config, title, body)
        elif channel.kind == "webhook":
            self._send_webhook(client, config, title, body, event)
        elif channel.kind == "email":
            self._send_email(config, title, body)
        else:  # pragma: no cover - schema restricts kinds
            raise ValueError(f"unsupported channel kind: {channel.kind}")

    @staticmethod
    def _send_bark(client: httpx.Client, config: dict[str, Any], title: str, body: str) -> None:
        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("bark channel requires config.url")
        payload: dict[str, Any] = {"title": title, "body": body, "group": "SteamList"}
        if config.get("sound"):
            payload["sound"] = config["sound"]
        if config.get("icon"):
            payload["icon"] = config["icon"]
        response = client.post(url, json=payload)
        response.raise_for_status()

    @staticmethod
    def _send_webhook(
        client: httpx.Client,
        config: dict[str, Any],
        title: str,
        body: str,
        event: PriceEvent,
    ) -> None:
        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("webhook channel requires config.url")
        method = str(config.get("method") or "POST").upper()
        if method not in WEBHOOK_METHODS:
            raise ValueError(f"unsupported webhook method: {method}")
        headers = config.get("headers") or {}
        payload = {
            "title": title,
            "body": body,
            "appid": event.appid,
            "rule": event.kind,
            "final_cents": event.final_cents,
            "discount_percent": event.discount_percent,
            "currency": event.currency,
            "occurred_at": to_iso(utcnow()),
        }
        response = client.request(method, url, json=payload, headers=headers)
        response.raise_for_status()

    @staticmethod
    def _send_email(config: dict[str, Any], title: str, body: str) -> None:
        host = str(config.get("host") or "").strip()
        from_addr = str(config.get("from_addr") or "").strip()
        recipients = [str(addr) for addr in (config.get("to_addrs") or []) if str(addr).strip()]
        if not host or not from_addr or not recipients:
            raise ValueError("email channel requires config.host, config.from_addr and config.to_addrs")
        port = int(config.get("port") or (465 if config.get("use_ssl") else 587))

        message = EmailMessage()
        message["Subject"] = title
        message["From"] = from_addr
        message["To"] = ", ".join(recipients)
        message.set_content(body)

        context = ssl.create_default_context()
        if config.get("use_ssl", port == 465):
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
        try:
            if not config.get("use_ssl", port == 465) and config.get("use_tls", port == 587):
                smtp.starttls(context=context)
            username = config.get("username")
            if username:
                smtp.login(str(username), str(config.get("password") or ""))
            smtp.send_message(message)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
