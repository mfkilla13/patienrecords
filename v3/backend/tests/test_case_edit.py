from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import demo
from medqt3.api import create_app


def test_fix_admission_data(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    cid = demo.create(conn)
    client = TestClient(create_app(path))
    got = client.get(f"/api/cases/{cid}/edit").json()
    form = got["form"]
    assert form["surname"] == "Тестова" and got["otherCases"] == 0 and form["admittedDate"]

    bad = client.put(f"/api/cases/{cid}/edit", json={**form, "dob": "2099-08-30"})
    assert bad.status_code == 422 and "Дата рождения" in bad.json()["detail"]
    late = client.put(f"/api/cases/{cid}/edit", json={**form, "admittedDate": "2026-12-31"})
    assert late.status_code == 422
    first = conn.execute("SELECT MIN(substr(recorded_at,1,10)) FROM records WHERE case_id = ? AND kind = 'diary'", (cid,)).fetchone()[0]
    after = client.put(f"/api/cases/{cid}/edit", json={**form, "admittedDate": first[:8] + str(int(first[8:]) + 1).zfill(2)})
    assert after.status_code == 422 and "записи раньше" in after.json()["detail"]

    ok = client.put(f"/api/cases/{cid}/edit", json={**form, "surname": "Тестовая", "dob": "1951-03-04", "medCard": "123",
                                                    "dxClinical": "Незрелая катаракта OD", "channel": "самообращение",
                                                    "residence": "иногородний"})
    assert ok.status_code == 200
    card = client.get(f"/api/cases/{cid}").json()
    assert card["patient"]["surname"] == "Тестовая" and card["patient"]["dob"] == "1951-03-04" and card["medCard"] == "123"
    assert card["diagnosis"]["clinical"] == "Незрелая катаракта OD"
    again = client.get(f"/api/cases/{cid}/edit").json()["form"]
    assert (again["channel"], again["residence"]) == ("самообращение", "иногородний")
    assert client.put(f"/api/cases/{cid}/edit", json={**form, "surname": ""}).status_code == 422
    assert client.get("/api/cases/nope/edit").status_code == 404



def test_delete_a_case_made_by_mistake(tmp_path):
    path = tmp_path / "t.db"
    store.connect(path).close()
    client = TestClient(create_app(path))

    def admit(surname):
        body = {"surname": surname, "name": "Анна", "dob": "1960-01-02", "admittedDate": "2026-10-20",
                "admittedTime": "10:00", "dxAdmission": "Незрелая катаракта OD"}
        r = client.post("/api/admissions", json=body)
        assert r.status_code == 201
        return r.json()["caseId"]

    first, second = admit("Верная"), admit("Ошибкина")
    assert client.get("/api/dictionaries").json()["nextNumber"] == "3"
    form = client.get(f"/api/cases/{second}/edit").json()
    assert form["records"] == 0 and form["printed"] == 0

    r = client.delete(f"/api/cases/{second}")
    assert r.status_code == 200 and r.json()["patientDeleted"] is True and "before_delete" in r.json()["savedAs"]
    assert [p["caseId"] for p in client.get("/api/department").json()["patients"]] == [first]
    assert client.get(f"/api/cases/{second}").status_code == 404
    assert client.get("/api/patients/search", params={"q": "ошибк"}).json() == []
    assert client.get("/api/dictionaries").json()["nextNumber"] == "2"      # the last number is free again
    assert client.delete(f"/api/cases/{second}").status_code == 404
    assert any(b["kind"] == "before_delete" for b in client.get("/api/backups").json()["items"])


def test_vis_with_correction_on_one_eye_is_written_per_eye():
    from medqt3 import exam
    d = exam.normal_exam()
    d.update(vis_od="0,8", vis_os="0,9", vis_correction_od="с коррекцией", vis_od_corr="-1,5", vis_od_result="1,0",
             vis_correction_os="пусто", vgd_od="25", vgd_os="23")
    h = exam.render_html(d)
    assert "0,8 с коррекцией -1,5 D = 1,0" in h and "OS =" in h and ">0,9<" in h and "ВГД" in h
    d.update(vis_correction_od="пусто")
    assert "OD =" not in exam.render_html(d)          # no correction: the usual OD/OS fraction
