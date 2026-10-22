"""Pydantic request/response models - the frontend API contract.

Money values are always integer cents. Timestamps are ISO-8601 UTC strings
ending in ``Z``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class GameOut(BaseModel):
    appid: int
    name: str
    header_image: str
    short_description: str = ""
    developers: str = ""
    publishers: str = ""
    genres: str = ""
    release_date: str = ""
    is_free: bool = False


class StateOut(BaseModel):
    cc: str
    currency: str
    current_initial_cents: int
    current_final_cents: int
    current_discount_percent: int
    available: bool
    atl_cents: int | None = None
    atl_first_at: str | None = None
    atl_last_at: str | None = None
    atl_hit_count: int = 0
    first_change_at: str | None = None
    last_checked_at: str | None = None


class WatchItemOut(BaseModel):
    appid: int
    name: str
    header_image: str
    cc: str
    note: str = ""
    sort_order: int = 0
    notify_enabled: bool = False
    target_price_cents: int | None = None
    discount_alert_threshold: int | None = None
    created_at: str
    # flattened state for convenient card rendering
    currency: str = ""
    current_initial_cents: int = 0
    current_final_cents: int = 0
    current_discount_percent: int = 0
    available: bool = True
    atl_cents: int | None = None
    atl_hit_count: int = 0
    atl_last_at: str | None = None
    last_checked_at: str | None = None
    record_started_at: str | None = None


class WatchlistSummary(BaseModel):
    count: int = 0
    discounting_count: int = 0
    atl_count: int = 0
    below_target_count: int = 0
    last_checked_at: str | None = None


class WatchlistResponse(BaseModel):
    items: list[WatchItemOut] = Field(default_factory=list)
    summary: WatchlistSummary


class AddWatchRequest(BaseModel):
    appid: int = Field(gt=0)
    cc: str | None = None
    target_price_cents: int | None = Field(default=None, ge=0)
    discount_alert_threshold: int | None = Field(default=None, ge=1, le=100)
    note: str = ""
    notify_enabled: bool = False


class PatchWatchRequest(BaseModel):
    target_price_cents: int | None = Field(default=None, ge=0)
    discount_alert_threshold: int | None = Field(default=None, ge=1, le=100)
    note: str | None = None
    notify_enabled: bool | None = None
    sort_order: int | None = None


class SearchItemOut(BaseModel):
    appid: int
    name: str
    header_image: str
    price_cents: int | None = None
    currency: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchItemOut] = Field(default_factory=list)


class GameDetailResponse(BaseModel):
    game: GameOut
    watch: WatchItemOut


class SeriesPointOut(BaseModel):
    t: str
    final: int
    initial: int
    discount: int
    available: bool


class SeriesResponse(BaseModel):
    appid: int
    range: str
    start: str | None = None
    end: str
    points: list[SeriesPointOut] = Field(default_factory=list)
    record_started_at: str | None = None
    currency: str = ""


class StatsResponse(BaseModel):
    appid: int
    stats: dict[str, Any]
    record_started_at: str | None = None


class ChannelIn(BaseModel):
    kind: Literal["bark", "email", "webhook"]
    name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ChannelOut(ChannelIn):
    id: int


class SettingsOut(BaseModel):
    poll_enabled: bool
    poll_interval_hours: int
    poll_time: str
    cc: str
    lang: str
    steamid: str = ""
    proxy_url: str = ""
    wishlist_enabled: bool = True
    wishlist_last_import_at: str | None = None
    next_poll_at: str | None = None
    meta_refresh_at: str | None = None
    channels: list[ChannelOut] = Field(default_factory=list)


class SettingsPatch(BaseModel):
    poll_enabled: bool | None = None
    poll_interval_hours: int | None = Field(default=None, ge=1, le=168)
    poll_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    cc: str | None = Field(default=None, min_length=2, max_length=8)
    lang: str | None = Field(default=None, min_length=2, max_length=16)
    steamid: str | None = None
    proxy_url: str | None = None
    wishlist_enabled: bool | None = None
    channels: list[ChannelIn] | None = None

    @field_validator("poll_time")
    @classmethod
    def _valid_poll_time(cls, value: str | None) -> str | None:
        if value is None:
            return value
        hour, minute = value.split(":")
        if not 0 <= int(hour) <= 23 or not 0 <= int(minute) <= 59:
            raise ValueError("poll_time must be a valid HH:MM time")
        return value


class WishlistImportRequest(BaseModel):
    steamid: str | None = None
    limit: int = Field(default=200, ge=1, le=500)


class WishlistImportResponse(BaseModel):
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    appids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class JobRunOut(BaseModel):
    id: int
    job_type: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    checked_count: int = 0
    changed_count: int = 0
    error: str = ""


class JobStatusResponse(BaseModel):
    running: bool = False
    current: JobRunOut | None = None
    last: JobRunOut | None = None
    next_poll_at: str | None = None


class RefreshResponse(BaseModel):
    job_id: int
    status: str = "started"


class NotificationTestRequest(BaseModel):
    channel_id: int | None = None


class ChannelTestResult(BaseModel):
    channel_id: int
    name: str
    kind: str
    ok: bool
    error: str = ""


class NotificationTestResponse(BaseModel):
    results: list[ChannelTestResult] = Field(default_factory=list)


class NotificationLogOut(BaseModel):
    id: int
    appid: int | None = None
    game_name: str = ""
    rule: str
    title: str
    body: str
    status: str
    error: str = ""
    created_at: str
    sent_at: str | None = None


class NotificationLogResponse(BaseModel):
    items: list[NotificationLogOut] = Field(default_factory=list)


class BackupOut(BaseModel):
    name: str
    size_bytes: int
    created_at: str
    download_url: str


class BackupListResponse(BaseModel):
    backups: list[BackupOut] = Field(default_factory=list)
    latest: BackupOut | None = None
