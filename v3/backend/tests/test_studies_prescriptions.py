import json

import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import demo, studies
from medqt3.api import create_app


@pytest.fixture()
def setup(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    case_id = demo.create(conn)
    return TestClient(create_app(path)), conn, case_id


def test_typed_study_is_stored_as_29_and_reads_back(setup):
    client, conn, case_id = setup
    body = {"date": "2026-10-21", "type": "ОАК", "fields": {"hemoglobin": "128", "esr": "21", "wbc": "6,1"}}
    sid = client.post(f"/api/cases/{case_id}/studies", json=body).json()["id"]
    row = conn.execute("SELECT kind, data_json FROM studies WHERE id = ?", (sid,)).fetchone()
    data = json.loads(row["data_json"])
    assert row["kind"] == "ОАК" and data["schema"] == "diagnostic_form_v1" and data["fields"]["esr"] == "21"

    s = next(x for x in client.get(f"/api/cases/{case_id}/studies").json()["studies"] if x["id"] == sid)
    assert s["result"] == "Hb 128; Л 6,1; СОЭ 21" and s["flags"] == ["СОЭ ↑"]
    card = client.get(f"/api/cases/{case_id}").json()
    assert any(x["summary"] == "Hb 128; Л 6,1; СОЭ 21" for x in card["studies"])


def test_free_form_and_29_texts():
    assert studies.results_text({"schema": "free_text", "name": "RW", "text": "отр."}) == "отр."
    assert studies.results_text({"schema": "diagnostic_form_v1", "type": "Сахар крови",
                                 "fields": {"value": "3,7", "note": ""}}) == "Глюкоза: 3,7 ммоль/л"
    assert studies.results_text({"schema": "diagnostic_form_v1", "type": "Флюорография (ФГ)",
                                 "fields": {"number": "53270", "result": "без патологии"}}) == \
        "№ флюорографии: 53270\nРезультат: без патологии"
    assert studies.flags({"schema": "diagnostic_form_v1", "type": "Сахар крови", "fields": {"value": "3,7"}}) == []


def test_exam_plan_is_matched_by_aliases(setup):
    client, conn, case_id = setup
    exam = conn.execute("SELECT id, data_json FROM records WHERE case_id = ? AND kind = 'primary_exam'", (case_id,)).fetchone()
    data = json.loads(exam["data_json"]) | {"selected_examinations": ["ОАК", "Сахар Крови", "RW", "ренген легких"]}
    with conn:
        conn.execute("UPDATE records SET data_json = ? WHERE id = ?", (json.dumps(data, ensure_ascii=False), exam["id"]))
    for t in ("ОАК", "МРС"):
        client.post(f"/api/cases/{case_id}/studies", json={"date": "2026-10-21", "type": t, "fields": {}})
    plan = {p["name"]: p["done"] for p in client.get(f"/api/cases/{case_id}/studies").json()["plan"]}
    assert plan == {"ОАК": True, "Сахар Крови": False, "RW": True, "ренген легких": False}


def test_study_edit_delete_and_archive_lock(setup):
    client, conn, case_id = setup
    sid = client.post(f"/api/cases/{case_id}/studies", json={"date": "21.10.2026", "type": "Свободная форма",
                                                              "name": "Суточное ВГД", "text": "18–22"}).json()["id"]
    assert client.put(f"/api/studies/{sid}", json={"date": "2026-10-22", "type": "Свободная форма",
                                                   "name": "Суточное ВГД", "text": "18–21"}).status_code == 200
    s = client.get(f"/api/cases/{case_id}/studies").json()["studies"]
    assert [(x["name"], x["date"], x["result"]) for x in s] == [("Суточное ВГД", "2026-10-22", "18–21")]
    assert client.post(f"/api/cases/{case_id}/studies", json={"date": "вчера", "type": "ОАК"}).status_code == 422
    with conn:
        conn.execute("UPDATE cases SET status = 'archived' WHERE id = ?", (case_id,))
    assert client.delete(f"/api/studies/{sid}").status_code == 409
    with conn:
        conn.execute("UPDATE cases SET status = 'active' WHERE id = ?", (case_id,))
    assert client.delete(f"/api/studies/{sid}").status_code == 200
    assert client.get(f"/api/cases/{case_id}/studies").json()["studies"] == []


def test_prescriptions_add_several_cancel_and_templates(setup):
    client, conn, case_id = setup
    lst = client.get(f"/api/cases/{case_id}/prescriptions").json()
    assert "стол 15" in lst["templates"]["stol"] and lst["items"] == []

    r = client.post(f"/api/cases/{case_id}/prescriptions", json={
        "category": "drugs", "names": ["Тобрадекс", "Индоколлир 0,1%"], "method": "местно OD", "freq": "4 раза в сутки"})
    assert r.status_code == 201 and len(r.json()["ids"]) == 2
    client.post(f"/api/cases/{case_id}/prescriptions", json={"category": "stol", "names": ["стол 15"], "method": "в/в"})
    items = client.get(f"/api/cases/{case_id}/prescriptions").json()["items"]
    assert len(items) == 3 and all(i["dateFrom"] and i["dateTo"] is None and i["active"] for i in items)
    stol = next(i for i in items if i["category"] == "stol")
    assert stol["method"] == "" and stol["freq"] == ""          # no method/frequency for a diet

    drug = next(i for i in items if i["name"] == "Тобрадекс")
    client.post(f"/api/prescriptions/{drug['id']}/cancel")             # cancelled today: no longer active
    assert not next(i for i in client.get(f"/api/cases/{case_id}/prescriptions").json()["items"] if i["id"] == drug["id"])["active"]
    client.post(f"/api/prescriptions/{drug['id']}/cancel", params={"on": "2000-01-01"})
    drug = next(i for i in client.get(f"/api/cases/{case_id}/prescriptions").json()["items"] if i["id"] == drug["id"])
    assert drug["dateTo"] == "2000-01-01" and not drug["active"]

    t = client.get(f"/api/cases/{case_id}/prescriptions").json()["templates"]
    t["drugs"] = ["Тобрадекс", "Тобрадекс", " "]
    assert client.put("/api/prescription-templates", json={"templates": t}).json()["drugs"] == ["Тобрадекс"]
    assert client.get(f"/api/cases/{case_id}/prescriptions").json()["templates"]["drugs"] == ["Тобрадекс"]

    # Prescribed drugs join the discharge's treatment list.
    assert "Индоколлир 0,1%" in client.get(f"/api/cases/{case_id}/discharge").json()["form"]["treatment_summary"]


def test_prescription_sheet_prints_all_sections_with_dates(tmp_path):
    import pypdfium2
    from medqt3 import db as store
    from medqt3 import demo
    from medqt3.api import create_app
    from fastapi.testclient import TestClient

    path = tmp_path / "t.db"
    conn = store.connect(path)
    cid = demo.create(conn)
    client = TestClient(create_app(path))
    client.post(f"/api/cases/{cid}/prescriptions", json={"category": "stol", "names": ["стол 9"], "method": "", "freq": "",
                                                           "date_from": "2026-10-20", "date_to": None})
    ids = client.post(f"/api/cases/{cid}/prescriptions", json={"category": "drugs", "names": ["Тауфон 4% капли"], "method": "местно",
                                                                 "freq": "3 раза в сутки", "date_from": "2026-10-20", "date_to": "2026-10-25"}).json()["ids"]
    assert ids
    assert client.get(f"/api/cases/{cid}/prescriptions/pages").json() == {"pages": 1}
    pdf = pypdfium2.PdfDocument(client.get(f"/api/cases/{cid}/prescriptions/pdf").content)
    text = pdf[0].get_textpage().get_text_bounded()
    for s in ("ЛИСТ НАЗНАЧЕНИЙ", "Тестова Анна Ивановна", "Стол, режим", "стол 9", "Препараты", "Тауфон 4% капли",
              "местно", "3 раза в сутки", "20.10.2026", "25.10.2026", "Лечащий врач"):
        assert s in text, s
    r = client.get(f"/api/cases/{cid}/prescriptions/pages/1.png")
    assert r.status_code == 200 and r.headers["x-page-count"] == "1"
    assert client.get("/api/cases/nope/prescriptions/pdf").status_code == 404
