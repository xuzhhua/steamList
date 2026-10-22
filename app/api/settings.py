"""Application settings endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import NotificationChannel
from ..schemas import SettingsOut, SettingsPatch
from ..services.scheduler import compute_next_poll
from ..services.settings_store import get_settings, update_settings
from ..timeutil import utcnow
from .serializers import settings_out

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> SettingsOut:
    return settings_out(db)


@router.put("", response_model=SettingsOut)
def write_settings(payload: SettingsPatch, request: Request, db: Session = Depends(get_db)) -> SettingsOut:
    data = payload.model_dump(exclude_unset=True)
    channels = data.pop("channels", None)
    try:
        update_settings(db, data)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored = get_settings(db)
    tz_name = request.app.state.settings.timezone
    update_settings(db, {"next_poll_at": compute_next_poll(stored, utcnow(), tz_name)})

    if channels is not None:
        db.query(NotificationChannel).delete()
        for channel in channels:
            db.add(
                NotificationChannel(
                    kind=channel["kind"],
                    name=channel.get("name") or channel["kind"],
                    config_json=json.dumps(channel.get("config") or {}, ensure_ascii=False),
                    enabled=bool(channel.get("enabled", True)),
                )
            )
    db.commit()
    return settings_out(db)
