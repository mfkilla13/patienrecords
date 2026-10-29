from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from medqt3 import backups, demo
from medqt3 import db as store
from medqt3.api import create_app


@pytest.fixture()
def setup(tmp_path):
    path = tmp_path / "data" / "medqt.db"
    conn = store.connect(path)
    demo.create(conn)
    return TestClient(create_app(path)), conn, path


def test_manual_backup_is_checked_and_listed(setup):
    client, conn, path = setup
    r = client.post("/api/backups")
    assert r.status_code == 201 and r.json()["extraError"] is None
    lst = client.get("/api/backups").json()
    assert lst["folder"].endswith("backups") and len(lst["items"]) == 1
    item = lst["items"][0]
    assert item["kind"] == "manual" and item["size"] > 0 and lst["last"] == item["at"]
    assert sorted(p.name for p in (path.parent / "backups").iterdir()) == [item["name"]]   # one file, no -wal/-shm
    copy = store.connect(path.parent / "backups" / item["name"])
    assert copy.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1


def test_restore_brings_data_back_and_saves_current_state_first(setup):
    client, conn, path = setup
    name = client.post("/api/backups").json()["name"]
    with conn:
        conn.execute("DELETE FROM print_positions")
        conn.execute("UPDATE cases SET outcome = 'испорчено'")
    r = client.post(f"/api/backups/{name}/restore")
    assert r.status_code == 200 and "before_restore" in r.json()["savedAs"]
    assert conn.execute("SELECT outcome FROM cases").fetchone()[0] != "испорчено"
    kinds = {x["kind"] for x in client.get("/api/backups").json()["items"]}
    assert kinds == {"manual", "before_restore"}


def test_only_own_files_can_be_restored_or_deleted(setup):
    client, conn, path = setup
    (path.parent / "other.db").write_bytes(b"x")
    assert client.post("/api/backups/..%2Fother.db/restore").status_code in (404, 405)
    assert client.post("/api/backups/other.db/restore").status_code == 404
    assert client.delete("/api/backups/medqt.db").status_code == 404


def test_rotation_keeps_recent_monthly_and_manual(setup):
    client, conn, path = setup
    start = datetime(2025, 1, 1, 9, 0)
    for i in range(400):                       # more than a year of daily copies
        backups.make(conn, path, "auto", now=start + timedelta(days=i))
    backups.make(conn, path, "manual", now=start)
    items = backups.listing(conn, path)["items"]
    autos = [x for x in items if x["kind"] == "auto"]
    assert len([x for x in items if x["kind"] == "manual"]) == 1
    # 14 newest + the last of each of 12 months (the newest month is already among the 14)
    assert 14 < len(autos) <= 14 + 12
    assert autos[0]["at"].startswith("2026-02-04")


def test_daily_due_and_extra_folder(setup, tmp_path):
    client, conn, path = setup
    assert backups.due(path)
    backups.make(conn, path, "auto", now=datetime.now() - timedelta(hours=2))
    assert not backups.due(path)
    assert backups.due(path, now=datetime.now() + timedelta(hours=23))

    assert client.put("/api/backups/extra-dir", json={"path": str(tmp_path / "нет")}).status_code == 422
    usb = tmp_path / "usb"
    usb.mkdir()
    assert client.put("/api/backups/extra-dir", json={"path": str(usb)}).json()["extraDir"] == str(usb)
    name = client.post("/api/backups").json()["name"]
    assert (usb / name).is_file()
    usb_gone = str(tmp_path / "unplugged")
    with conn:
        conn.execute("UPDATE meta SET value = ? WHERE key = 'backup_extra_dir'", (usb_gone,))
    r = client.post("/api/backups").json()
    assert r["extraError"] and client.get("/api/backups").json()["extraError"]
