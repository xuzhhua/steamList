"""Notification log and channel test endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import Game, NotificationChannel, NotificationLog
from ..schemas import (
    ChannelTestResult,
    NotificationLogOut,
    NotificationLogResponse,
    NotificationTestRequest,
    NotificationTestResponse,
)
from ..services.notifier import Notifier
from ..timeutil import to_iso

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/log", response_model=NotificationLogResponse)
def list_log(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> NotificationLogResponse:
    rows = db.execute(
        select(NotificationLog).order_by(NotificationLog.id.desc()).limit(limit)
    ).scalars().all()
    names: dict[int, str] = {}
    items: list[NotificationLogOut] = []
    for row in rows:
        game_name = ""
        if row.appid is not None:
            if row.appid not in names:
                game = db.get(Game, row.appid)
                names[row.appid] = game.name if game else ""
            game_name = names[row.appid]
        items.append(
            NotificationLogOut(
                id=row.id,
                appid=row.appid,
                game_name=game_name,
                rule=row.rule,
                title=row.title,
                body=row.body,
                status=row.status,
                error=row.error or "",
                created_at=to_iso(row.created_at) or "",
                sent_at=to_iso(row.sent_at),
            )
        )
    return NotificationLogResponse(items=items)


@router.post("/test", response_model=NotificationTestResponse)
def test_notifications(
    payload: NotificationTestRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> NotificationTestResponse:
    if payload.channel_id is not None:
        channel = db.get(NotificationChannel, payload.channel_id)
        if channel is None:
            raise HTTPException(status_code=404, detail=f"channel {payload.channel_id} not found")
        channels = [channel]
    else:
        channels = list(db.execute(select(NotificationChannel).order_by(NotificationChannel.id)).scalars())

    notifier = Notifier(db, transport=getattr(request.app.state, "notifier_transport", None))
    results = []
    for channel in channels:
        ok, error = notifier.send_test(channel)
        results.append(
            ChannelTestResult(
                channel_id=channel.id,
                name=channel.name,
                kind=channel.kind,
                ok=ok,
                error=error,
            )
        )
    return NotificationTestResponse(results=results)
