from __future__ import annotations

from datetime import timedelta

from app.services.backup import create_backup, list_backups
from app.timeutil import utcnow


def test_create_and_list_backups(settings):
    first = create_backup(settings.db_path, settings.backups_dir, now=utcnow())
    assert first.path.is_file()
    assert first.size_bytes > 0
    assert first.name.startswith("steamlist-")
    assert first.name.endswith(".db")

    backups = list_backups(settings.backups_dir)
    assert [info.name for info in backups] == [first.name]


def test_prune_keeps_latest(settings):
    start = utcnow() - timedelta(hours=10)
    for index in range(5):
        create_backup(settings.db_path, settings.backups_dir, now=start + timedelta(hours=index), keep=2)
    backups = list_backups(settings.backups_dir)
    assert len(backups) == 2
    # newest first
    assert backups[0].created_at >= backups[1].created_at


def test_backup_api_roundtrip(client, app):
    created = client.post("/api/backup")
    assert created.status_code == 201
    body = created.json()
    assert body["name"].endswith(".db")
    assert body["size_bytes"] > 0
    assert body["download_url"].endswith(body["name"])

    listing = client.get("/api/backup").json()
    assert listing["latest"]["name"] == body["name"]
    assert any(item["name"] == body["name"] for item in listing["backups"])

    download = client.get("/api/backup/download", params={"name": body["name"]})
    assert download.status_code == 200
    assert download.content.startswith(b"SQLite format 3\x00")
    assert (app.state.settings.backups_dir / body["name"]).is_file()


def test_backup_download_rejects_traversal(client):
    assert client.get("/api/backup/download", params={"name": "../steamlist.db"}).status_code == 400
    assert client.get("/api/backup/download", params={"name": "missing.db"}).status_code == 404
