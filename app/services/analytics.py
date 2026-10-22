"""Analytics over persisted price change points.

Definitions (see design doc):
* ATL = lowest *available* final price > 0; ties resolve to the earliest time.
* atl_hit_count = number of times the price entered the ATL from a higher value
  (the very first observation counts as one).
* A discount episode is a maximal run of points with ``discount_percent > 0``;
  the episode ends when a point has no discount (or now, if it is still open).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PriceChange
from ..timeutil import to_iso, utcnow

RANGE_DAYS: dict[str, int | None] = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
    "1y": 365,
    "all": None,
}


@dataclass(frozen=True)
class Point:
    at: datetime
    initial_cents: int
    final_cents: int
    discount_percent: int
    available: bool


@dataclass(frozen=True)
class Episode:
    start: datetime
    end: datetime
    max_discount: int


def load_points(session: Session, appid: int, cc: str | None = None) -> list[Point]:
    stmt = select(PriceChange).where(PriceChange.appid == appid)
    if cc:
        stmt = stmt.where(PriceChange.cc == cc)
    stmt = stmt.order_by(PriceChange.changed_at.asc(), PriceChange.id.asc())
    return [
        Point(
            at=row.changed_at,
            initial_cents=row.initial_cents,
            final_cents=row.final_cents,
            discount_percent=row.discount_percent,
            available=row.available,
        )
        for row in session.execute(stmt).scalars()
    ]


def range_start(range_key: str, now: datetime | None = None) -> datetime | None:
    if range_key not in RANGE_DAYS:
        raise ValueError(f"unsupported range: {range_key}")
    days = RANGE_DAYS[range_key]
    if days is None:
        return None
    return (now or utcnow()) - timedelta(days=days)


def build_series(
    points: list[Point],
    start: datetime | None,
    end: datetime,
) -> list[dict[str, Any]]:
    """Return step-function points; prepend the last point before ``start``."""
    if not points:
        return []
    selected: list[Point] = []
    if start is not None:
        anchor: Point | None = None
        for point in points:
            if point.at <= start:
                anchor = point
            else:
                break
        if anchor is not None:
            selected.append(anchor)
        selected.extend(p for p in points if p.at > start)
    else:
        selected = list(points)
    return [
        {
            "t": to_iso(p.at),
            "final": p.final_cents,
            "initial": p.initial_cents,
            "discount": p.discount_percent,
            "available": p.available,
        }
        for p in selected
    ]


def _episodes(points: list[Point], now: datetime) -> list[Episode]:
    episodes: list[Episode] = []
    current_start: datetime | None = None
    current_discount = 0
    for point in points:
        if point.discount_percent > 0:
            if current_start is None:
                current_start = point.at
                current_discount = point.discount_percent
            else:
                current_discount = max(current_discount, point.discount_percent)
        else:
            if current_start is not None:
                episodes.append(Episode(current_start, point.at, current_discount))
                current_start = None
                current_discount = 0
    if current_start is not None:
        episodes.append(Episode(current_start, now, current_discount))
    return episodes


def compute_stats(points: list[Point], now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    empty = {
        "first_change_at": None,
        "last_change_at": None,
        "change_count": 0,
        "days_tracked": 0,
        "current_initial_cents": None,
        "current_final_cents": None,
        "current_discount_percent": 0,
        "available": None,
        "atl_cents": None,
        "atl_first_at": None,
        "atl_last_at": None,
        "atl_hit_count": 0,
        "discount_event_count": 0,
        "discount_days": 0.0,
        "max_discount_percent": 0,
        "avg_discount_percent": 0.0,
        "avg_interval_days": None,
        "last_discount_at": None,
        "discounting": False,
    }
    if not points:
        return empty

    atl_cents: int | None = None
    atl_first: datetime | None = None
    atl_last: datetime | None = None
    atl_hits = 0
    prev_final: int | None = None
    for point in points:
        if point.available and point.final_cents > 0:
            if atl_cents is None or point.final_cents < atl_cents:
                atl_cents = point.final_cents
                atl_first = point.at
                atl_last = point.at
                atl_hits += 1
            elif point.final_cents == atl_cents and prev_final is not None and prev_final > atl_cents:
                atl_hits += 1
                atl_last = point.at
        if point.available and point.final_cents > 0:
            prev_final = point.final_cents

    episodes = _episodes(points, now)
    discount_days = sum((e.end - e.start).total_seconds() for e in episodes) / 86400.0
    max_discount = max((e.max_discount for e in episodes), default=0)
    avg_discount = sum(e.max_discount for e in episodes) / len(episodes) if episodes else 0.0
    intervals = [
        (b.start - a.start).total_seconds() / 86400.0
        for a, b in zip(episodes, episodes[1:])
    ]
    last = points[-1]
    return {
        "first_change_at": to_iso(points[0].at),
        "last_change_at": to_iso(last.at),
        "change_count": len(points),
        "days_tracked": int((now - points[0].at).total_seconds() // 86400),
        "current_initial_cents": last.initial_cents,
        "current_final_cents": last.final_cents,
        "current_discount_percent": last.discount_percent,
        "available": last.available,
        "atl_cents": atl_cents,
        "atl_first_at": to_iso(atl_first),
        "atl_last_at": to_iso(atl_last),
        "atl_hit_count": atl_hits,
        "discount_event_count": len(episodes),
        "discount_days": round(discount_days, 2),
        "max_discount_percent": max_discount,
        "avg_discount_percent": round(avg_discount, 1),
        "avg_interval_days": round(sum(intervals) / len(intervals), 1) if intervals else None,
        "last_discount_at": to_iso(episodes[-1].start) if episodes else None,
        "discounting": last.discount_percent > 0,
    }
