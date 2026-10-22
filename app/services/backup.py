"""SQLite backups: create snapshot files and serve them for download."""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..timeutil import utcnow

BACKUP_PREFIX = "steamlist-"
BACKUP_SUFFIX = ".db"


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    size_bytes: int
    created_at: datetime


def create_backup(db_path: Path, backups_dir: Path, now: datetime | None = None, keep: int = 14) -> BackupInfo:
    """Copy the live SQLite database with the backup API, then prune old snapshots."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or utcnow()).strftime("%Y%m%d-%H%M%S")
    target = backups_dir / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    counter = 1
    while target.exists():
        target = backups_dir / f"{BACKUP_PREFIX}{stamp}-{counter}{BACKUP_SUFFIX}"
        counter += 1

    source = sqlite3.connect(str(db_path))
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    stat = target.stat()
    info = BackupInfo(
        name=target.name,
        path=target,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime),
    )
    _prune(backups_dir, keep)
    return info


def _prune(backups_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    backups = list_backups(backups_dir)
    for info in backups[keep:]:
        try:
            info.path.unlink()
        except OSError:
            pass


def list_backups(backups_dir: Path) -> list[BackupInfo]:
    if not backups_dir.exists():
        return []
    infos: list[BackupInfo] = []
    for path in backups_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"):
        if not path.is_file():
            continue
        stat = path.stat()
        infos.append(
            BackupInfo(
                name=path.name,
                path=path,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    # snapshot names embed a sortable timestamp, which is more reliable than mtime
    infos.sort(key=lambda info: info.name, reverse=True)
    return infos


def copy_backup_to(info: BackupInfo, destination: Path) -> Path:
    """Copy a backup to ``destination`` (used by tests and export flows)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(info.path, destination)
    return destination
