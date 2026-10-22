from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("STEAMLIST_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STEAMLIST_ENABLE_SCHEDULER", "false")
    from app.config import Settings

    s = Settings()
    s.ensure_dirs()
    return s


@pytest.fixture()
def app(settings):
    from app.main import create_app

    return create_app(settings)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(app):
    return app.state.db


@pytest.fixture()
def session(db):
    s = db.session()
    try:
        yield s
    finally:
        s.close()
