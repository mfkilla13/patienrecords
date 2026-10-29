from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3.api import create_app


def _client(tmp_path):
    path = tmp_path / "t.db"
    store.connect(path).close()
    c = TestClient(create_app(path))
    c.db_path = path
    return c


def _admit(client, **kw):
    body = {"surname": "Петрова", "name": "Ольга", "patronymic": "Ивановна", "dob": "1950-02-03", "medCard": "77",
            "admittedDate": "2026-10-20", "admittedTime": "10:00", "dxAdmission": "Незрелая катаракта OD"}
    body.update(kw)
    r = client.post("/api/admissions", json=body)
    assert r.status_code == 201, r.text
    return r.json()["caseId"]


def _group(data, key):
    return next(g for g in data["groups"] if g["key"] == key)["items"]


def test_clean_database_has_no_issues(tmp_path):
    client = _client(tmp_path)
    _admit(client)
    data = client.get("/api/checks").json()
    assert data["total"] == 0
    assert client.get("/api/department").json()["summary"]["issues"] == 0


def test_found_issues_link_to_the_fix_and_can_be_confirmed(tmp_path):
    client = _client(tmp_path)
    cid = _admit(client, dob="2026-03-01", medCard="")      # this year: the form only warns, so it gets in
    conn = store.connect(client.db_path)
    with conn:   # a 2.9 diary dated before the admission
        conn.execute("INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at)"
                     " VALUES ('r1', ?, 'diary', '2026-10-10', '{}', '2026-10-10', '2026-10-10')", (cid,))
    data = client.get("/api/checks").json()
    dob = _group(data, "dob_year")
    assert len(dob) == 1 and dob[0]["link"] == f"/case/{cid}/edit" and "01.03.2026" in dob[0]["detail"]
    early = _group(data, "record_early")
    assert early[0]["link"] == f"/case/{cid}/diary/r1" and "20.10.2026" in early[0]["detail"]
    assert len(_group(data, "no_med_card")) == 1
    assert data["total"] == 3 and client.get("/api/department").json()["summary"]["issues"] == 3

    after = client.post("/api/checks/confirm", json={"check": "dob_year", "item": dob[0]["item"]}).json()
    assert after["total"] == 2 and _group(after, "dob_year") == [] and after["confirmed"] == 1

    # fixing the card number removes the row by itself
    form = client.get(f"/api/cases/{cid}/edit").json()["form"]
    assert client.put(f"/api/cases/{cid}/edit", json={**form, "medCard": "123"}).status_code == 200
    assert client.get("/api/checks").json()["total"] == 1
