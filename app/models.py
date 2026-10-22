"""SQLAlchemy ORM models for SteamList."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .timeutil import utcnow


class Game(Base):
    __tablename__ = "games"

    appid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    header_image: Mapped[str] = mapped_column(Text, default="")
    short_description: Mapped[str] = mapped_column(Text, default="")
    developers: Mapped[str] = mapped_column(String(255), default="")
    publishers: Mapped[str] = mapped_column(String(255), default="")
    genres: Mapped[str] = mapped_column(String(255), default="")
    release_date: Mapped[str] = mapped_column(String(64), default="")
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WatchItem(Base):
    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appid: Mapped[int] = mapped_column(ForeignKey("games.appid", ondelete="CASCADE"), unique=True, index=True)
    cc: Mapped[str] = mapped_column(String(8), default="cn")
    target_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    discount_alert_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PriceChange(Base):
    __tablename__ = "price_changes"
    __table_args__ = (
        UniqueConstraint("appid", "cc", "changed_at", name="uq_price_change_point"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appid: Mapped[int] = mapped_column(ForeignKey("games.appid", ondelete="CASCADE"), index=True)
    cc: Mapped[str] = mapped_column(String(8), default="cn")
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    initial_cents: Mapped[int] = mapped_column(Integer, default=0)
    final_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class WatchState(Base):
    __tablename__ = "watch_state"

    appid: Mapped[int] = mapped_column(ForeignKey("games.appid", ondelete="CASCADE"), primary_key=True)
    cc: Mapped[str] = mapped_column(String(8), default="cn")
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    current_initial_cents: Mapped[int] = mapped_column(Integer, default=0)
    current_final_cents: Mapped[int] = mapped_column(Integer, default=0)
    current_discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    atl_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atl_first_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    atl_last_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    atl_hit_count: Mapped[int] = mapped_column(Integer, default=0)
    first_change_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="bark")  # bark | email | webhook
    name: Mapped[str] = mapped_column(String(64), default="")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule: Mapped[str] = mapped_column(String(16), default="")
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    channel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # sent | failed | skipped
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), default="poll")
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checked_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
