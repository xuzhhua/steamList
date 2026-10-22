"""Application settings loaded from environment variables (.env supported)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration.

    All values can be overridden with ``STEAMLIST_``-prefixed env vars, e.g.
    ``STEAMLIST_DATA_DIR=/app/data`` or ``STEAMLIST_CC=us``.
    """

    model_config = SettingsConfigDict(
        env_prefix="STEAMLIST_",
        env_file=str(PROJECT_ROOT / ".env"),
        extra="ignore",
    )

    data_dir: Path = PROJECT_ROOT / "data"
    db_filename: str = "steamlist.db"
    timezone: str = "Asia/Shanghai"
    default_cc: str = "cn"
    default_lang: str = "schinese"
    proxy_url: str | None = None
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Build a fresh Settings instance (re-reads env vars; handy in tests)."""
    return Settings()
