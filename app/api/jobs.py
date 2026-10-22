"""Scheduler job endpoints: manual refresh and status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models import JobRun
from ..schemas import JobStatusResponse, RefreshResponse
from ..services.scheduler import PollBusy
from ..services.settings_store import get_settings as load_settings
from .serializers import job_run_out

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/refresh", response_model=RefreshResponse, status_code=202)
def trigger_refresh(request: Request) -> RefreshResponse:
    poller = request.app.state.poller
    try:
        job_id = poller.start_background()
    except PollBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RefreshResponse(job_id=job_id, status="started")


@router.get("/status", response_model=JobStatusResponse)
def job_status(request: Request, db: Session = Depends(get_db)) -> JobStatusResponse:
    poller = request.app.state.poller
    running = poller.running
    current = None
    if running:
        current = db.execute(
            select(JobRun).where(JobRun.status == "running").order_by(JobRun.id.desc())
        ).scalars().first()
    last = db.execute(
        select(JobRun).where(JobRun.status != "running").order_by(JobRun.id.desc())
    ).scalars().first()
    settings = load_settings(db)
    return JobStatusResponse(
        running=running,
        current=job_run_out(current),
        last=job_run_out(last),
        next_poll_at=settings.get("next_poll_at"),
    )
