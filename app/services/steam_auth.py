"""Steam account login via the QR-code flow of ``IAuthenticationService``.

The public wishlist endpoint only works for public profiles.  When a Steam
account is linked here, SteamList keeps a refresh token (locally, in the app
database) and uses it to read the owner's private wishlist.

The flow is simple enough to talk to the WebAPI directly with JSON:

1. ``BeginAuthSessionViaQR`` -> ``challenge_url`` (rendered as a QR code) and
   the ``client_id``/``request_id`` used for polling.
2. The user confirms the login in the Steam mobile app.
3. ``PollAuthSessionStatus`` -> access token + refresh token.
4. ``GenerateAccessTokenForApp`` renews the short-lived access token later.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import httpx

from ..config import Settings
from ..timeutil import utcnow

logger = logging.getLogger("steamlist")

AUTH_BASE = "https://api.steampowered.com/IAuthenticationService/"
BEGIN_QR_URL = AUTH_BASE + "BeginAuthSessionViaQR/v1/"
POLL_QR_URL = AUTH_BASE + "PollAuthSessionStatus/v1/"
ACCESS_TOKEN_URL = AUTH_BASE + "GenerateAccessTokenForApp/v1/"
REVOKE_TOKEN_URL = AUTH_BASE + "RevokeToken/v1/"

USER_AGENT = "SteamList/0.1 (self-hosted price tracker)"
SESSION_TTL_SECONDS = 300
SESSION_RETENTION_SECONDS = 900
ACCESS_TOKEN_SAFETY_SECONDS = 120


class SteamAuthError(RuntimeError):
    """Raised when Steam rejects a login or the stored session is invalid."""


@dataclass
class QRSession:
    session_id: str
    client_id: str
    request_id: str
    challenge_url: str
    interval: int
    created_at: datetime
    status: str = "pending"
    account_name: str | None = None
    steamid: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "account_name": self.account_name,
            "steamid": self.steamid,
            "message": self.error,
        }


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Read (without verifying) the claims of a Steam JWT access token."""
    parts = (token or "").split(".")
    if len(parts) < 2:
        raise SteamAuthError("Steam 返回的登录令牌格式不正确")
    segment = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(segment.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:  # pragma: no cover - defensive
        raise SteamAuthError("无法解析 Steam 登录令牌") from exc


def token_steamid(access_token: str) -> str:
    claims = decode_jwt_claims(access_token)
    steamid = str(claims.get("sub") or "")
    if not steamid:
        raise SteamAuthError("Steam 登录令牌缺少账号信息")
    return steamid


def token_expires_at(access_token: str) -> float:
    claims = decode_jwt_claims(access_token)
    try:
        return float(claims.get("exp") or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class _CachedToken:
    token: str
    expires_at: float


class SteamAuthService:
    """Owns QR login sessions and cached access tokens (single process)."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 25.0,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._timeout = timeout
        self._sessions: dict[str, QRSession] = {}
        self._tokens: dict[str, _CachedToken] = {}

    # -- http plumbing -----------------------------------------------------
    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": self._timeout,
            "headers": {"User-Agent": USER_AGENT},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        elif self._settings.proxy_url:
            kwargs["proxy"] = self._settings.proxy_url
        return httpx.AsyncClient(**kwargs)

    async def _call(self, url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        params = {"input_json": json.dumps(payload, separators=(",", ":"))}
        try:
            async with self._client() as client:
                response = await client.post(url, params=params)
        except httpx.HTTPError as exc:
            raise SteamAuthError(f"无法连接 Steam 登录服务：{exc}") from exc
        if response.status_code != 200:
            raise SteamAuthError(f"Steam 登录服务返回 HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:  # pragma: no cover - Steam always returns JSON
            raise SteamAuthError("Steam 登录服务返回了无法解析的响应") from exc
        data = body.get("response") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise SteamAuthError("Steam 登录服务返回了意外的响应")
        error = data.get("error")
        if isinstance(error, dict) and error:
            raise SteamAuthError(f"Steam 登录失败（erresult={error.get('eresult', '未知')}）")
        return data

    # -- QR session lifecycle ---------------------------------------------
    def _purge(self) -> None:
        now = utcnow().timestamp()
        stale = [
            key for key, session in self._sessions.items()
            if now - session.created_at.timestamp() > SESSION_RETENTION_SECONDS
        ]
        for key in stale:
            self._sessions.pop(key, None)

    async def begin_qr(self) -> QRSession:
        self._purge()
        data = await self._call(BEGIN_QR_URL, {"device_friendly_name": "SteamList", "website_id": "Store"})
        challenge_url = str(data.get("challenge_url") or "")
        client_id = str(data.get("client_id") or "")
        request_id = str(data.get("request_id") or "")
        if not challenge_url or not client_id or not request_id:
            raise SteamAuthError("Steam 未返回有效的二维码登录信息")
        session = QRSession(
            session_id=uuid.uuid4().hex,
            client_id=client_id,
            request_id=request_id,
            challenge_url=challenge_url,
            interval=max(1, int(data.get("interval") or 5)),
            created_at=utcnow(),
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> QRSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        age = utcnow().timestamp() - session.created_at.timestamp()
        if session.status == "pending" and age > SESSION_TTL_SECONDS:
            session.status = "expired"
            session.error = "二维码已过期，请重新生成"
        return session

    async def poll_qr(self, session_id: str) -> QRSession:
        session = self.get_session(session_id)
        if session is None:
            raise SteamAuthError("登录会话不存在或已过期，请重新生成二维码")
        if session.status != "pending":
            return session
        data = await self._call(POLL_QR_URL, {"client_id": session.client_id, "request_id": session.request_id})
        tokens = data.get("tokens") or {}
        if isinstance(tokens, dict) and tokens.get("refresh_token"):
            session.refresh_token = str(tokens["refresh_token"])
            session.access_token = str(tokens.get("access_token") or "")
            session.account_name = str(data.get("account_name") or "") or None
            try:
                session.steamid = token_steamid(session.access_token) if session.access_token else None
            except SteamAuthError:
                session.steamid = None
            session.status = "success"
            logger.info("steam qr login succeeded for %s", session.account_name or session.steamid)
        elif data.get("had_remote_interaction"):
            session.status = "scanned"
        return session

    # -- tokens ------------------------------------------------------------
    async def access_token(self, refresh_token: str, steamid: str) -> str:
        """Return a valid (cached) access token for the linked account."""
        if not refresh_token:
            raise SteamAuthError("尚未登录 Steam 账号")
        cached = self._tokens.get(refresh_token)
        now = time.time()
        if cached is not None and cached.expires_at - ACCESS_TOKEN_SAFETY_SECONDS > now:
            return cached.token
        data = await self._call(ACCESS_TOKEN_URL, {"refresh_token": refresh_token, "steamid": steamid})
        token = str(data.get("access_token") or "")
        if not token:
            raise SteamAuthError("Steam 登录已失效，请在设置页重新扫码登录")
        expires_at = token_expires_at(token) or (now + 1800)
        self._tokens[refresh_token] = _CachedToken(token=token, expires_at=expires_at)
        return token

    async def revoke(self, refresh_token: str, steamid: str) -> None:
        """Best-effort token revocation when the account is unlinked."""
        if not refresh_token:
            return
        try:
            await self._call(REVOKE_TOKEN_URL, {"refresh_token": refresh_token, "steamid": steamid})
        except SteamAuthError as exc:  # pragma: no cover - network dependent
            logger.info("steam token revocation failed: %s", exc)
        finally:
            self._tokens.pop(refresh_token, None)

    # -- synchronous helpers for the API layer -----------------------------
    def begin_qr_sync(self) -> QRSession:
        return asyncio.run(self.begin_qr())

    def poll_qr_sync(self, session_id: str) -> QRSession:
        return asyncio.run(self.poll_qr(session_id))

    def access_token_sync(self, refresh_token: str, steamid: str) -> str:
        return asyncio.run(self.access_token(refresh_token, steamid))

    def revoke_sync(self, refresh_token: str, steamid: str) -> None:
        try:
            asyncio.run(self.revoke(refresh_token, steamid))
        except RuntimeError:  # pragma: no cover - already inside a loop
            pass


__all__ = [
    "QRSession",
    "SteamAuthError",
    "SteamAuthService",
    "decode_jwt_claims",
    "token_steamid",
]
