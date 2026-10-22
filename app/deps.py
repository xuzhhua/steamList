"""Shared FastAPI dependencies."""
from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.db
    session = db.session()
    try:
        yield session
    finally:
        session.close()
