import json

import pypdfium2
import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import exam
from medqt3.api import create_app


@pytest.fixture()
def client(tmp_path):
    path = tmp_path / "t.db"
    store.connect(path).close()
    c = TestClient(create_app(path))
    c.db_path = path
    return c


def admit(client, **kw):
    body = {"surname": "Кузнецова", "name": "Анна", "patronymic": "Сергеевна", "dob": "1956-05-14",
            "city": "Тирасполь", "street": "ул. 25 Октября", "house": "112, кв. 7", "medCard": "104387",
            "admittedDate": "2026-10-29", "admittedTime": "09:25", "dxAdmission": "Незрелая катаракта OD",
            "dxComorbid": "Гипертоническая болезнь II ст."}
    body.update(kw)
    return client.post("/api/admissions", json=body)


def test_admission_creates_patient_and_numbered_case(client):
    r = admit(client)
    assert r.status_code == 201 and r.json()["number"] == "1"
    card = client.get(f"/api/cases/{r.json()['caseId']}").json()
    assert card["patient"]["surname"] == "Кузнецова" and card["admittedAt"] == "2026-10-29T09:25"
    assert card["diagnosis"]["admission"] == "Незрелая катаракта OD"
    dep = client.get("/api/department").json()
    assert [p["number"] for p in dep["patients"]] == ["1"]
    assert client.get("/api/dictionaries").json()["nextNumber"] == "2"


def test_readmission_reuses_patient_and_refuses_a_second_active_case(client):
    first = admit(client).json()
    found = client.get("/api/patients/search", params={"q": "кузн"}).json()
    assert len(found) == 1 and found[0]["lastCase"]["number"] == "1"
    again = admit(client, patientId=found[0]["id"])
    assert again.status_code == 409 and "уже в отделении" in again.json()["detail"]

    conn = store.connect(client.db_path)
    with conn:   # discharged after the first eye
        conn.execute("UPDATE cases SET status = 'archived' WHERE id = ?", (first["caseId"],))
    second = admit(client, patientId=found[0]["id"], surname="", city="Бендеры", dxAdmission="Незрелая катаракта OS")
    assert second.status_code == 201 and second.json()["patientId"] == first["patientId"]
    assert second.json()["number"] == "2"
    assert client.get("/api/patients/search", params={"q": "Кузнецова Анна"}).json()[0]["city"] == "Бендеры"

    # The earlier exam can be taken over: the draft offers it without measurements.
    data = exam.normal_exam() | {"visit_date": "2026-10-01", "complaints": "раньше", "vis_od": "0,2"}
    conn2 = store.connect(client.db_path)
    with conn2:
        conn2.execute("UPDATE cases SET status = 'active' WHERE id = ?", (first["caseId"],))
    client.post(f"/api/cases/{first['caseId']}/exam", json={"data": data})
    prev = client.get(f"/api/cases/{second.json()['caseId']}/exam-draft").json()["previous"]
    assert prev["number"] == "1" and prev["data"]["complaints"] == "раньше" and "vis_od" not in prev["data"]


def test_admission_validation(client):
    assert admit(client, surname="").status_code == 422
    assert admit(client, dxAdmission="").status_code == 422
    assert admit(client, medCard="12a").status_code == 422
    assert admit(client, admittedTime="9:5").status_code == 422


def test_exam_draft_suggests_template_by_diagnosis_and_prefills(client):
    case_id = admit(client).json()["caseId"]
    d = client.get(f"/api/cases/{case_id}/exam-draft").json()
    suggested = [t["name"] for t in d["templates"] if t["suggested"]]
    assert suggested == ["Катаракта, плановая"]
    assert d["prefill"]["diagnosis_free"] == "Незрелая катаракта OD"
    assert d["existing"] is None and d["previous"] is None
    template = next(t for t in d["templates"] if t["suggested"])["data"]
    assert template["local"]["Хрусталик"]["od_selected"] == ["неравномерно мутный"]
    assert "vis_od" not in template and "diagnosis_free" not in template   # templates carry no measurements or diagnoses


def test_saving_exam_builds_29_html_updates_case_and_prints(client):
    case_id = admit(client).json()["caseId"]
    data = exam.normal_exam()
    data.update({"visit_date": "2026-10-29", "visit_time": "09:40", "complaints": "на снижение зрения",
                 "vis_od": "0,1", "vis_correction_od": "n.k. (не коррег.)", "vis_os": "0,6", "vgd_od": "21", "vgd_os": "18",
                 "diagnosis_free": "Незрелая катаракта OD", "custom_comorbid_diagnosis": "ГБ II ст.",
                 "selected_examinations": ["ОАК", "ЭКГ"]})
    data["local"]["Глазное дно"]["od_selected"] = ["не просматривается"]
    r = client.post(f"/api/cases/{case_id}/exam", json={"data": data})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert client.post(f"/api/cases/{case_id}/exam", json={"data": data}).status_code == 409   # one exam per case

    card = client.get(f"/api/cases/{case_id}").json()
    assert card["diagnosis"]["clinical"] == "Незрелая катаракта OD" and card["diagnosis"]["comorbid"] == "ГБ II ст."
    saved = client.get(f"/api/cases/{case_id}/exam-draft").json()["existing"]["data"]
    # 2.9's rule: a fundus that cannot be seen hides the vitreous, vessels and retina of that eye.
    assert saved["local"]["Стекловидное тело"]["od_selected"][0] == "не просматривается"
    assert saved["local"]["Сетчатка"]["os_selected"] == ["прилежит"]

    plan = client.get(f"/api/cases/{case_id}/print-plan").json()
    job = client.post(f"/api/cases/{case_id}/print-jobs", json={"recordIds": [plan["records"][0]["id"]], "mode": "new"}).json()
    text = pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{job['jobId']}/pdf").content)[0].get_textpage().get_text_range()
    for expected in ("29.10.2026", "09:40", "Первичный осмотр", "Жалобы:", "Анамнез:", "Объективно:",
                     "Структура", "не просматривается", "Клинический диагноз", "Незрелая катаракта OD",
                     "Сопутствующий:", "План обследования:", "ОАК, ЭКГ"):
        assert expected in text, expected

    client.post(f"/api/print-jobs/{job['jobId']}/confirm")
    data["complaints"] = "изменено"
    assert client.put(f"/api/cases/{case_id}/exam/{rid}", json={"data": data}).status_code == 409   # printed: locked


def test_render_matches_29_wording():
    d = exam.normal_exam()
    d.update({"complaints": "на боли", "vis_od": "0,3", "vis_os": "0,6", "vis_correction_os": "с коррекцией",
              "vis_os_corr": "+1,5", "vis_os_result": "0,8", "selected_diagnoses_od": ["Катаракта"]})
    h = exam.render_html(d, "Петрова Е. В.")
    assert '<div class="section"><span class="title">Жалобы:</span> на боли</div>' in h
    assert "- Туберкулез, кожвен-заболевания: отрицает<br>" in h
    assert "+1,5 D" in h and "0,8" in h
    assert "<u>клинический диагноз</u>: <b>Катаракта OD</b>" in h
    assert "Петрова Е. В. __________________" in h


def test_missing_local_rows_are_not_filled_with_norm():
    d = exam.complete({"local": {"Хрусталик": {"od_selected": ["полупрозрачный"]}}})
    assert list(d["local"])[0] == "Хрусталик"
    assert d["local"]["Веки"]["od_selected"] == []          # not «без особенностей»


def test_template_save_and_use_count(client):
    case_id = admit(client).json()["caseId"]
    data = exam.normal_exam() | {"complaints": "мой шаблон", "vis_od": "0,5", "diagnosis_free": "X"}
    tid = client.post("/api/exam-templates", json={"name": "Птеригиум", "keywords": "птеригиум", "data": data}).json()["id"]
    t = next(t for t in client.get(f"/api/cases/{case_id}/exam-draft").json()["templates"] if t["id"] == tid)
    assert t["data"]["complaints"] == "мой шаблон" and "vis_od" not in t["data"]
    client.post(f"/api/cases/{case_id}/exam", json={"data": exam.normal_exam() | {"visit_date": "2026-10-29"}, "templateId": tid})
    t = next(t for t in client.get(f"/api/cases/{case_id}/exam-draft").json()["templates"] if t["id"] == tid)
    assert t["useCount"] == 1
    client.delete(f"/api/exam-templates/{tid}")
    assert all(t["id"] != tid for t in client.get(f"/api/cases/{case_id}/exam-draft").json()["templates"])
