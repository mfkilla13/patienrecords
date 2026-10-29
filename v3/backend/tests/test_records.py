import pypdfium2
import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3.api import create_app


@pytest.fixture()
def env(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO patients (id, surname, name, created_at, updated_at) VALUES ('p1', 'Тестова', 'Анна', ?, ?)", (ts, ts))
        conn.execute("INSERT INTO cases (id, patient_id, number, admitted_at, status, created_at, updated_at)"
                     " VALUES ('c1', 'p1', '1', '2026-10-01T09:00', 'active', ?, ?)", (ts, ts))
    return TestClient(create_app(path)), conn


def card_record(client, rid):
    return next(r for r in client.get("/api/cases/c1").json()["records"] if r["id"] == rid)


def test_protocol_and_text_record_show_print_and_lock(env):
    client, conn = env
    proto = {"date": "2026-10-03", "time": "10:15", "title": "Факоэмульсификация катаракты OD", "text": "Разрез 2,2 мм.\nИОЛ в мешке."}
    pid = client.post("/api/cases/c1/records/operation_protocol", json=proto).json()["id"]
    tid = client.post("/api/cases/c1/records/other", json={"date": "2026-10-02", "time": "", "title": "Консилиум",
                                                           "text": "Показана операция OD."}).json()["id"]
    p = card_record(client, pid)
    assert p["title"] == "Факоэмульсификация катаракты OD" and p["editable"] and p["recordedAt"] == "2026-10-03T10:15"
    t = card_record(client, tid)
    assert t["kindLabel"] == "Консилиум" and t["sections"] == [{"label": "", "text": "Показана операция OD."}]
    assert client.get("/api/cases/c1").json()["unprinted"] == 2
    assert client.get("/api/department").json()["patients"][0]["stage"] == "post_op"

    plan = client.get("/api/cases/c1/print-plan").json()["records"]
    assert [r["kindLabel"] for r in plan] == ["Консилиум", "Протокол операции"] and all(r["printable"] for r in plan)
    job = client.post("/api/cases/c1/print-jobs", json={"recordIds": [tid, pid], "mode": "new"}).json()
    pdf = pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{job['jobId']}/pdf").content)
    text = pdf[0].get_textpage().get_text_range()
    assert "Консилиум" in text and "Показана операция OD." in text and "Протокол операции" in text
    assert client.post(f"/api/print-jobs/{job['jobId']}/confirm").status_code == 200

    assert not card_record(client, tid)["editable"]
    assert client.put(f"/api/records/{tid}", json={"date": "2026-10-02", "title": "Консилиум", "text": "другое"}).status_code == 409
    assert client.delete(f"/api/records/{pid}").status_code == 409


def test_edit_validate_delete_and_archive(env):
    client, conn = env
    post = lambda body: client.post("/api/cases/c1/records/other", json=body)
    assert post({"date": "2026-09-30", "title": "Консилиум", "text": "x"}).json()["detail"] == "Дата записи раньше даты поступления"
    assert post({"date": "2099-01-01", "title": "Консилиум", "text": "x"}).status_code == 422
    assert post({"date": "2026-10-02", "time": "25:00", "title": "Консилиум", "text": "x"}).status_code == 422
    assert post({"date": "2026-10-02", "title": "", "text": "x"}).status_code == 422
    assert client.post("/api/cases/c1/records/diary", json={"date": "2026-10-02", "title": "x", "text": "x"}).status_code == 422
    assert client.post("/api/cases/c1/records/operation_protocol", json={"date": "2026-10-02"}).status_code == 422

    rid = post({"date": "2026-10-02", "time": "12:00", "title": "Предоперационный эпикриз", "text": "Готова к операции"}).json()["id"]
    r = client.put(f"/api/records/{rid}", json={"date": "2026-10-04", "time": "", "title": "Предоперационный эпикриз", "text": "  Готова.\n"})
    assert r.status_code == 200
    got = client.get(f"/api/records/{rid}").json()
    assert (got["date"], got["time"], got["text"], got["kind"]) == ("2026-10-04", "", "Готова.", "other")

    with conn:
        conn.execute("UPDATE cases SET status = 'archived' WHERE id = 'c1'")
    assert client.delete(f"/api/records/{rid}").status_code == 409
    with conn:
        conn.execute("UPDATE cases SET status = 'active' WHERE id = 'c1'")
    assert client.delete(f"/api/records/{rid}").status_code == 200
    assert all(r["id"] != rid for r in client.get("/api/cases/c1").json()["records"])


def test_operation_templates(env):
    client, conn = env
    first = client.get("/api/record-options").json()
    assert "Консилиум" in first["textTitles"] and first["templates"][0]["name"].startswith("Факоэмульсификация")
    t = client.post("/api/operation-templates", json={"name": "Антиглаукоматозная  операция", "description": "Синустрабекулэктомия."}).json()
    assert t[0] == {"name": "Антиглаукоматозная операция", "description": "Синустрабекулэктомия."} and len(t) == 2
    t = client.post("/api/operation-templates", json={"name": "антиглаукоматозная операция", "description": "Новый текст"}).json()
    assert len(t) == 2 and t[0]["description"] == "Новый текст"
    t = client.request("DELETE", "/api/operation-templates", params={"name": t[0]["name"]}).json()
    assert len(t) == 1
