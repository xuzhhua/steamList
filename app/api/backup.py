"""Backup listing, creation and download endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..schemas import BackupListResponse, BackupOut
from ..services.backup import BackupInfo, create_backup, list_backups
from ..timeutil import to_iso

router = APIRouter(prefix="/backup", tags=["backup"])


def _out(info: BackupInfo) -> BackupOut:
    return BackupOut(
        name=info.name,
        size_bytes=info.size_bytes,
        created_at=to_iso(info.created_at.replace(tzinfo=None)) or "",
        download_url=f"/api/backup/download?name={info.name}",
    )


@router.get("", response_model=BackupListResponse)
def list_all(request: Request) -> BackupListResponse:
    infos = list_backups(request.app.state.settings.backups_dir)
    backups = [_out(info) for info in infos]
    return BackupListResponse(backups=backups, latest=backups[0] if backups else None)


@router.post("", response_model=BackupOut, status_code=201)
def create(request: Request) -> BackupOut:
    settings = request.app.state.settings
    info = create_backup(settings.db_path, settings.backups_dir)
    return _out(info)


@router.get("/download")
def download(request: Request, name: str = Query(default="")) -> FileResponse:
    settings = request.app.state.settings
    if not name or Path(name).name != name or not name.endswith(".db"):
        raise HTTPException(status_code=400, detail="invalid backup name")
    path = settings.backups_dir / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"backup {name} not found")
    return FileResponse(path, media_type="application/octet-stream", filename=name)
