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
