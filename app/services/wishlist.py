"""Import Steam wishlists into the local watchlist."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import WatchItem
from ..timeutil import utcnow
from .pricing import PriceResult, ensure_game, ensure_placeholder_game, ingest_prices
from .steam_client import GameMeta


@dataclass
class ImportReport:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    appids: list[int] = field(default_factory=list)


def import_wishlist(
    session: Session,
    appids: list[int],
    metas: dict[int, GameMeta],
    prices: dict[int, PriceResult | None],
    cc: str,
    now: datetime | None = None,
) -> ImportReport:
    """Add new wishlist games to the watchlist and ingest their current prices."""
    now = now or utcnow()
    report = ImportReport()
    existing = set(session.execute(select(WatchItem.appid)).scalars())
    next_sort = session.execute(select(func.max(WatchItem.sort_order))).scalar() or 0

    new_appids: list[int] = []
    for appid in appids:
        if appid in existing:
            report.skipped += 1
            continue
        existing.add(appid)
        next_sort += 10
        ensure_placeholder_game(session, appid)
        meta = metas.get(appid)
        if meta is not None:
            ensure_game(session, meta, now=now)
        session.add(WatchItem(appid=appid, cc=cc, sort_order=next_sort))
        new_appids.append(appid)
        report.appids.append(appid)
        report.imported += 1

    session.flush()
    if new_appids:
        outcome = ingest_prices(
            session,
            {appid: prices.get(appid) for appid in new_appids},
            cc,
            now=now,
        )
        report.failed = len(outcome.failed)
    return report
