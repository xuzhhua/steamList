"""Steam QR-code login endpoints.

The refresh token is stored in the local SQLite settings table only; it never
leaves the container. Access tokens are derived on demand and cached in memory.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..deps import get_db
from ..schemas import QRStartResponse, QRStatusResponse, SteamSessionResponse
from ..services.settings_store import get_settings as load_settings, update_settings
from ..services.steam_auth import SESSION_TTL_SECONDS, SteamAuthError
from ..timeutil import to_iso, utcnow
from .serializers import steam_session_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/steam", tags=["steam-auth"])

DISCONNECTED_PATCH = {
    "steam_refresh_token": "",
    "steam_account_name": "",
    "steam_connected_at": None,
}


def _auth(request: Request):
    auth = getattr(request.app.state, "steam_auth", None)
    if auth is None:
        raise HTTPException(status_code=501, detail="Steam login is not enabled in this build")
    return auth


@router.post("/qr", response_model=QRStartResponse, status_code=201)
async def start_qr_login(request: Request) -> QRStartResponse:
    auth = _auth(request)
    try:
        session = await auth.begin_qr()
    except SteamAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return QRStartResponse(
        session_id=session.session_id,
        challenge_url=session.challenge_url,
        interval=session.interval,
        expires_in_seconds=SESSION_TTL_SECONDS,
    )


@router.get("/qr/{session_id}", response_model=QRStatusResponse)
async def poll_qr_login(session_id: str, request: Request, db: Session = Depends(get_db)) -> QRStatusResponse:
    auth = _auth(request)
    if auth.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="二维码会话不存在或已过期，请重新生成")
    try:
        session = await auth.poll_qr(session_id)
    except SteamAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if session.status == "success" and session.refresh_token:
        update_settings(
            db,
            {
                "steam_refresh_token": session.refresh_token,
                "steam_account_name": session.account_name or "",
                "steam_connected_at": to_iso(utcnow()),
                "steamid": session.steamid or "",
            },
        )
        db.commit()
        logger.info("steam account connected: %s (%s)", session.account_name, session.steamid)

    return QRStatusResponse(
        status=session.status,
        account_name=session.account_name,
        steamid=session.steamid,
        message=session.error,
    )


@router.get("/session", response_model=SteamSessionResponse)
def get_session_state(db: Session = Depends(get_db)) -> SteamSessionResponse:
    return steam_session_out(load_settings(db))


@router.delete("/session", response_model=SteamSessionResponse)
def disconnect(request: Request, db: Session = Depends(get_db)) -> SteamSessionResponse:
    stored = load_settings(db)
    refresh_token = str(stored.get("steam_refresh_token") or "")
    steamid = str(stored.get("steamid") or "")
    auth = getattr(request.app.state, "steam_auth", None)
    if refresh_token and auth is not None:
        try:
            auth.revoke_sync(refresh_token, steamid)
        except SteamAuthError as exc:  # revoked best effort
            logger.warning("steam token revoke failed: %s", exc)
    update_settings(db, DISCONNECTED_PATCH)
    db.commit()
    return steam_session_out(load_settings(db))
