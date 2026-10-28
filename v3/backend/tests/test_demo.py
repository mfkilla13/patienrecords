from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import demo
from medqt3.api import create_app


def test_demo_patient_is_printable_and_recreated_from_scratch(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    case_id = demo.create(conn)
    client = TestClient(create_app(path))

    dep = client.get("/api/department").json()
    assert [p["number"] for p in dep["patients"]] == ["ТЕСТ"]
    plan = client.get(f"/api/cases/{case_id}/print-plan").json()
    ids = [r["id"] for r in plan["records"]]
    assert len(ids) == 10 and all(r["printable"] and not r["printedAt"] for r in plan["records"])

    job = client.post(f"/api/cases/{case_id}/print-jobs", json={"recordIds": ids, "mode": "new"}).json()
    assert len(job["pages"]) >= 2                       # enough to try a second sheet
    client.post(f"/api/print-jobs/{job['jobId']}/confirm")

    assert client.get("/api/dictionaries").json()["nextNumber"] == "1"   # the test patient is not counted

    new_case = demo.create(conn)                        # recreate: previous prints are gone
    assert new_case != case_id
    assert conn.execute("SELECT COUNT(*) FROM print_positions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
    plan = client.get(f"/api/cases/{new_case}/print-plan").json()
    assert plan["state"] is None and not any(r["printedAt"] for r in plan["records"])
