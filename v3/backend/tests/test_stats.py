from datetime import date

from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import stats
from medqt3.api import create_app


def add(conn, n, admitted, discharged=None, status="archived", outcome="улучшение", dx="Катаракта OD"):
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO patients (id, surname, created_at, updated_at) VALUES (?, 'Т', ?, ?)", (f"p{n}", ts, ts))
        conn.execute("INSERT INTO cases (id, patient_id, number, admitted_at, discharged_at, status, outcome, dx_final,"
                     " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (f"c{n}", f"p{n}", str(n), admitted, discharged, status, outcome, dx, ts, ts))


def test_five_charts_and_grouping(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    add(conn, 1, "2026-03-02T09:00", "2026-03-11T12:00")                              # 10 bed-days
    add(conn, 2, "2026-03-20T09:00", "2026-04-03T12:00", outcome="Без перемен", dx="Глаукома OS")  # 15
    add(conn, 3, "2026-04-10T09:00", "2026-04-14", dx="")                             # 5
    add(conn, 4, "2026-04-28T09:00", None, status="active", dx="что-то редкое")
    s = stats.compute(conn, "2026-03-01", "2026-04-30", today=date(2026, 5, 1))
    assert s["group"] == "day" and len(s["admissions"]) == 61
    s = stats.compute(conn, "2026-01-01", "2026-12-31", today=date(2026, 5, 1))
    assert s["group"] == "month" and [x["label"] for x in s["admissions"][:3]] == ["янв 26", "фев 26", "мар 26"]
    by = {x["key"]: x for x in s["admissions"]}
    assert by["2026-03"]["value"] == 2 and by["2026-04"]["value"] == 2
    dis = {x["key"]: x["value"] for x in s["discharges"]}
    assert dis["2026-03"] == 1 and dis["2026-04"] == 2
    stay = {x["key"]: x["value"] for x in s["avgStay"]}
    assert stay["2026-03"] == 10 and stay["2026-04"] == 10 and stay["2026-05"] is None
    assert s["totals"] == {"admitted": 4, "discharged": 3, "avgStay": 10.0, "inDepartment": 1}
    assert [x["label"] for x in s["diagnoses"]] == ["Глаукома", "Катаракта", "Другое", "Не указан"]
    assert s["outcomes"] == [{"label": "Улучшение", "value": 2}, {"label": "Без перемен", "value": 1}]
    assert stats.compute(conn, None, None, today=date(2030, 1, 1))["group"] == "year"

    s = stats.compute(conn, "2026-03-01", "2026-03-31", today=date(2026, 3, 20))
    by = {d["date"]: d for d in s["daily"]}
    assert len(s["daily"]) == 20 and s["beds"] == 20                     # up to today only
    assert by["2026-03-02"]["inDepartment"] == 1 and by["2026-03-02"]["admitted"] == 1
    assert by["2026-03-11"]["inDepartment"] == 0                          # discharged that day: the bed is free
    assert by["2026-03-20"]["inDepartment"] == 1


def test_api_rejects_reversed_period(tmp_path):
    client = TestClient(create_app(tmp_path / "t.db"))
    assert client.get("/api/stats?date_from=2026-05-01&date_to=2026-04-01").status_code == 422
    assert client.get("/api/stats").json()["totals"]["admitted"] == 0
