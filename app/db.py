"""Database engine / session management."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_sqlite_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class Database:
    """Owns the engine and session factory for one data directory."""

    #: CDN hosts whose ``/steam/apps/`` tree stopped serving hashed asset paths.
    _LEGACY_CDN_PREFIXES = (
        "https://cdn.akamai.steamstatic.com/steam/apps/",
        "https://cdn.cloudflare.steamstatic.com/steam/apps/",
    )
    _ASSET_PREFIX = (
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/"
    )

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.engine = create_sqlite_engine(db_path)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        # Import models so that they are registered on Base.metadata.
        from . import models  # noqa: F401

        Base.metadata.create_all(self.engine)
        self._migrate_asset_urls()

    def _migrate_asset_urls(self) -> None:
        """Rewrite cover URLs saved before Steam moved assets to the shared CDN.

        Old rows point at ``cdn.akamai.steamstatic.com/steam/apps/...``; games with
        hashed asset folders 404 there. The new ``store_item_assets`` prefix serves
        both hashed and plain paths, so a prefix swap repairs every stored URL.
        """
        from sqlalchemy import text

        with self.engine.begin() as connection:
            for prefix in self._LEGACY_CDN_PREFIXES:
                connection.execute(
                    text(
                        "UPDATE games SET header_image = replace(header_image, :old, :new) "
                        "WHERE header_image LIKE :like"
                    ),
                    {"old": prefix, "new": self._ASSET_PREFIX, "like": prefix + "%"},
                )

    def session(self) -> Session:
        return self.session_factory()

    def dispose(self) -> None:
        self.engine.dispose()


def get_session() -> Iterator[Session]:
    """FastAPI dependency replaced per-app in ``app.main``."""
    raise RuntimeError("get_session dependency not configured")
