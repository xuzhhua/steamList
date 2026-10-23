"""Price polling: collect snapshots, track history, dispatch notifications."""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_, select

from ..db import Database
from ..models import Game, JobRun, WatchItem
from ..timeutil import from_iso, to_iso, utcnow
from . import pricing
from .notifier import Notifier
from .pricing import IngestResult, ingest_prices
from .settings_store import get_settings, update_settings
from .steam_client import SteamClient

logger = logging.getLogger(__name__)


class PollBusy(RuntimeError):
    """Raised when a poll is already in progress."""


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=dt_timezone.utc)


def compute_next_poll(
    settings: dict,
    now: datetime | None = None,
    tz_name: str = "Asia/Shanghai",
) -> str | None:
    """Return the next poll time as an ISO-8601 UTC string (or None if disabled)."""
    if not settings.get("poll_enabled", True):
        return None
    now = now or utcnow()
    interval = int(settings.get("poll_interval_hours") or 24)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - fall back to UTC for exotic tz names
        tz = dt_timezone.utc
    local_now = _as_utc(now).astimezone(tz)

    if interval != 24:
        due = local_now + timedelta(hours=interval)
    else:
        try:
            hour, minute = (int(part) for part in str(settings.get("poll_time") or "03:30").split(":"))
        except ValueError:
            hour, minute = 3, 30
        due = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due <= local_now:
            due += timedelta(days=1)
    return to_iso(due.astimezone(dt_timezone.utc).replace(tzinfo=None))


class PollService:
    def __init__(
        self,
        database: Database,
        client_factory,
        *,
        tz_name: str = "Asia/Shanghai",
        notifier_transport=None,
        meta_refresh_days: int = 7,
    ):
        self.database = database
        self.client_factory = client_factory
        self.tz_name = tz_name
        self.notifier_transport = notifier_transport
        self.meta_refresh_days = meta_refresh_days
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._running

    # -- public API -----------------------------------------------------
    def run_poll(self, now: datetime | None = None, notify: bool = True) -> int:
        """Run one poll synchronously and return the job run id."""
        self._begin()
        try:
            run_id = self._create_run(now)
            self._execute(run_id, now, notify)
            return run_id
        finally:
            self._end()

    def start_background(self, now: datetime | None = None) -> int:
        """Kick off a poll in a daemon thread; returns the job run id immediately."""
        self._begin()
        try:
            run_id = self._create_run(now)
        except Exception:
            self._end()
            raise
        self._thread = threading.Thread(
            target=self._thread_main,
            args=(run_id, now),
            name="steamlist-poll",
            daemon=True,
        )
        self._thread.start()
        return run_id

    def ensure_schedule(self, now: datetime | None = None) -> None:
        """Initialise next_poll_at on first boot when polling is enabled."""
        session = self.database.session()
        try:
            settings = get_settings(session)
            if settings.get("poll_enabled") and not settings.get("next_poll_at"):
                update_settings(session, {"next_poll_at": compute_next_poll(settings, now, self.tz_name)})
                session.commit()
        finally:
            session.close()

    def scheduled_tick(self) -> None:
        """APScheduler entry point: poll when due."""
        session = self.database.session()
        try:
            settings = get_settings(session)
        finally:
            session.close()
        if not settings.get("poll_enabled"):
            return
        next_at = settings.get("next_poll_at")
        if next_at:
            try:
                due = from_iso(next_at)
            except ValueError:
                due = None
            if due is not None and _as_utc(due) > _as_utc(utcnow()):
                return
        try:
            self.run_poll()
        except PollBusy:
            logger.info("scheduled poll skipped: a poll is already running")

    # -- internals ------------------------------------------------------
    def _begin(self) -> None:
        with self._lock:
            if self._running:
                raise PollBusy("a poll is already running")
            self._running = True

    def _end(self) -> None:
        with self._lock:
            self._running = False

    def _thread_main(self, run_id: int, now: datetime | None) -> None:
        try:
            self._execute(run_id, now, True)
        finally:
            self._end()

    def _create_run(self, now: datetime | None) -> int:
        session = self.database.session()
        try:
            run = JobRun(job_type="poll", status="running", started_at=now or utcnow())
            session.add(run)
            session.commit()
            return run.id
        finally:
            session.close()

    def _execute(self, run_id: int, now: datetime | None, notify: bool) -> None:
        now = now or utcnow()
        session = self.database.session()
        try:
            settings = get_settings(session)
            items = session.execute(select(WatchItem).order_by(WatchItem.id)).scalars().all()
            appids = [item.appid for item in items]
            cc = str(settings["cc"])
            lang = str(settings["lang"])

            prices: dict[int, object] = {}
            metas: dict[int, object] = {}
            outcome = IngestResult(checked=0, changed=0, failed=[], events=[])
            if appids:
                meta_due = self._meta_refresh_due(settings.get("meta_refresh_at"), now)
                meta_appids = appids if meta_due else self._missing_meta_appids(session, appids)
                client = self.client_factory(cc, lang)
                prices, metas = asyncio.run(self._collect(client, appids, meta_appids))
                if metas:
                    for meta in metas.values():
                        pricing.ensure_game(session, meta, now=now)
                if meta_due and metas:
                    update_settings(session, {"meta_refresh_at": to_iso(now)})
                outcome = ingest_prices(session, prices, cc, now=now)  # type: ignore[arg-type]
            session.commit()

            if notify and outcome.events:
                result = Notifier(session, transport=self.notifier_transport).notify(outcome.events, now)
                session.commit()
                logger.info(
                    "notifications: sent=%s failed=%s skipped=%s",
                    result.sent,
                    result.failed,
                    result.skipped,
                )

            next_poll = compute_next_poll(settings, now, self.tz_name)
            update_settings(session, {"next_poll_at": next_poll})

            run = session.get(JobRun, run_id)
            if run is not None:
                run.status = "success"
                run.finished_at = utcnow()
                run.checked_count = outcome.checked
                run.changed_count = outcome.changed
            session.commit()
        except Exception as exc:  # noqa: BLE001 - record failure and surface to caller
            session.rollback()
            logger.exception("price poll failed")
            run = session.get(JobRun, run_id)
            if run is not None:
                run.status = "error"
                run.error = str(exc)[:500]
                run.finished_at = utcnow()
                session.commit()
            raise
        finally:
            session.close()

    async def _collect(
        self, client: SteamClient, appids: list[int], meta_appids: list[int]
    ):
        try:
            prices = await client.fetch_prices(appids)
            metas = await client.fetch_metas(meta_appids) if meta_appids else {}
            return prices, metas
        finally:
            await client.aclose()

    def _missing_meta_appids(self, session, appids: list[int]) -> list[int]:
        """Watched games whose name, cover or description is still empty."""
        if not appids:
            return []
        rows = session.execute(
            select(Game.appid).where(
                Game.appid.in_(appids),
                or_(
                    Game.name == "",
                    Game.header_image == "",
                    Game.short_description == "",
                ),
            )
        ).scalars()
        missing = set(rows)
        # Games that were never stored at all also need metadata.
        known = set(
            session.execute(select(Game.appid).where(Game.appid.in_(appids))).scalars()
        )
        missing.update(set(appids) - known)
        return [appid for appid in appids if appid in missing]

    def _meta_refresh_due(self, last_iso: str | None, now: datetime) -> bool:
        if not last_iso:
            return True
        try:
            last = from_iso(last_iso)
        except ValueError:
            return True
        return _as_utc(now) - _as_utc(last) >= timedelta(days=self.meta_refresh_days)


def build_scheduler(service: PollService, interval_minutes: int = 5) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=dt_timezone.utc)
    scheduler.add_job(
        service.scheduled_tick,
        "interval",
        minutes=interval_minutes,
        id="steamlist-poll-tick",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
