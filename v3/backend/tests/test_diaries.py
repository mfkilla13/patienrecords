import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3.api import create_app

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO patients (id, surname, name, created_at, updated_at) VALUES ('p1', 'Тестова', 'Анна', ?, ?)", (ts, ts))
        for cid, status in (("c1", "active"), ("c2", "archived")):
            conn.execute(
                "INSERT INTO cases (id, patient_id, number, admitted_at, status, created_at, updated_at)"
                " VALUES (?, 'p1', ?, '2026-10-01T09:00', ?, ?, ?)", (cid, cid[1:], status, ts, ts))
    conn.close()
    return TestClient(create_app(tmp_path / "t.db"))


def diary(**kw):
    base = {"date": "2026-10-27", "time": "09:30", "bp": "130/80", "vis_od": "0,6", "vis_os": "0,5",
            "vgd_od": "18", "vgd_os": "19", "complaints": "нет", "od_text": "роговица прозрачная",
            "treatment": "продолжить", "vis_correction_od": "n.k. (не коррег.)"}
    base.update(kw)
    return base


def test_create_read_and_card(client):
    rid = client.post("/api/cases/c1/diaries", json=diary()).json()["id"]
    got = client.get(f"/api/diaries/{rid}").json()
    assert got["data"]["vis_od"] == "0,6" and got["data"]["time"] == "09:30"
    rec = next(r for r in client.get("/api/cases/c1").json()["records"] if r["id"] == rid)
    assert rec["vision"]["od"] == {"vis": "0,6", "status": "n.k.", "corr": "", "result": "", "iop": "18"}
    assert rec["editable"] is True
    assert rec["recordedAt"] == "2026-10-27T09:30"


def test_empty_time_today_is_filled_with_now(client):
    rid = client.post("/api/cases/c1/diaries", json=diary(date=TODAY, time="")).json()["id"]
    data = client.get(f"/api/diaries/{rid}").json()["data"]
    assert re.fullmatch(r"\d{2}:\d{2}", data["time"])
    rec = next(r for r in client.get("/api/cases/c1").json()["records"] if r["id"] == rid)
    assert rec["recordedAt"] == f"{TODAY}T{data['time']}"


def test_draft_copies_from_latest_previous_day(client):
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-26", od_text="старый"))
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-27", od_text="вчерашний"))
    d = client.get("/api/cases/c1/diary-draft", params={"day": "2026-10-28"}).json()
    assert d["previous"]["date"] == "2026-10-27"
    assert d["previous"]["data"]["od_text"] == "вчерашний"
    assert d["today"] is None and d["previousUnchanged"] is False


def test_unchanged_text_two_days_is_flagged(client):
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-26"))
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-27"))
    d = client.get("/api/cases/c1/diary-draft", params={"day": "2026-10-28"}).json()
    assert d["previousUnchanged"] is True


def test_update_and_printed_lock(client, tmp_path):
    rid = client.post("/api/cases/c1/diaries", json=diary()).json()["id"]
    assert client.put(f"/api/diaries/{rid}", json=diary(vis_od="0,7")).status_code == 200
    assert client.get(f"/api/diaries/{rid}").json()["data"]["vis_od"] == "0,7"
    conn = store.connect(tmp_path / "t.db")
    with conn:
        conn.execute("UPDATE records SET printed_at = '2026-10-27T12:00' WHERE id = ?", (rid,))
    r = client.put(f"/api/diaries/{rid}", json=diary(vis_od="0,8"))
    assert r.status_code == 409 and "напечатан" in r.json()["detail"]


def test_rejects_archived_case_and_bad_input(client):
    assert client.post("/api/cases/c2/diaries", json=diary()).status_code == 409
    assert client.post("/api/cases/nope/diaries", json=diary()).status_code == 404
    assert client.post("/api/cases/c1/diaries", json=diary(date="27.10.2026")).status_code == 422
    assert client.post("/api/cases/c1/diaries", json=diary(time="9:3")).status_code == 422


def test_round_lists_active_cases_with_today_and_previous(client):
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-27"))
    rows = client.get("/api/round", params={"day": "2026-10-28"}).json()["rows"]
    assert [r["caseId"] for r in rows] == ["c1"]
    assert rows[0]["previous"]["date"] == "2026-10-27" and rows[0]["today"] is None
    assert rows[0]["dayLabel"] == "день 28"
    client.post("/api/cases/c1/diaries", json=diary(date="2026-10-28"))
    rows = client.get("/api/round", params={"day": "2026-10-28"}).json()["rows"]
    assert rows[0]["today"]["recordId"]
