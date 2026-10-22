"""Application-level settings persisted in ``app_settings`` as JSON values."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting

DEFAULT_SETTINGS: dict[str, Any] = {
    "poll_enabled": True,
    "poll_interval_hours": 24,
    "poll_time": "03:30",
    "cc": "cn",
    "lang": "schinese",
    "steamid": "",
    "proxy_url": "",
    "wishlist_last_import_at": None,
    "next_poll_at": None,
    "meta_refresh_at": None,
    "wishlist_import_enabled": True,
}


def get_settings(session: Session) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    for row in session.execute(select(AppSetting)).scalars():
        try:
            merged[row.key] = json.loads(row.value_json)
        except (TypeError, ValueError):
            continue
    return merged


def update_settings(session: Session, patch: dict[str, Any]) -> dict[str, Any]:
    unknown = set(patch) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ValueError(f"unknown settings keys: {', '.join(sorted(unknown))}")
    for key, value in patch.items():
        payload = json.dumps(value, ensure_ascii=False)
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value_json=payload))
        else:
            row.value_json = payload
    session.flush()
    return get_settings(session)
