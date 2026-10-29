import pytest
from fastapi.testclient import TestClient

from medqt3 import archive
from medqt3 import db as store
from medqt3.api import create_app


def _case(conn, number, surname, dob, dx, admitted, discharged, outcome="улучшение", status="archived"):
    ts = store.now_iso()
    pid, cid = store.new_id(), store.new_id()
    conn.execute("INSERT INTO patients (id, surname, name, patronymic, dob, created_at, updated_at)"
                 " VALUES (?, ?, 'Анна', 'Ивановна', ?, ?, ?)", (pid, surname, dob, ts, ts))
    conn.execute("INSERT INTO cases (id, patient_id, number, admitted_at, discharged_at, status, outcome, dx_final,"
                 " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (cid, pid, number, admitted, discharged, status, outcome, dx, ts, ts))
    return cid


@pytest.fixture()
def client(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    with conn:
        _case(conn, "10", "Ёлкина", "1956-05-14", "Незрелая ктаракта OD", "2026-04-01T09:00", "2026-04-07T10:00")
        _case(conn, "11", "Петрова", "1949-07-04", "Глауком обоих глаз OU", "2026-04-20", "2026-04-25", "без перемен")
        _case(conn, "12", "Сидорова", "1960-01-01", "Птеригиум OS", "2026-05-02", "2026-05-04")
        _case(conn, "13", "Активная", "1970-01-01", "Катаракта OD", "2026-05-02", None, "", "active")
    return TestClient(create_app(path))


def test_groups_catch_typos():
    assert archive.dx_groups("Незрелая ктаракта OD. Артифакия OS") == ["Катаракта", "Артифакия"]
    assert archive.dx_groups("о\\у компенсированная глауком") == ["Глаукома"]
    assert archive.dx_groups("Абсцедирующий ячмень нижнего века OD") == ["Веки"]
    assert archive.dx_groups("Острый иридоциклит OD") == ["Увеит, иридоциклит"]
    assert archive.dx_groups("") == ["Не указан"] and archive.dx_groups("Энофтальм") == ["Другое"]


def test_only_archived_newest_first_with_days_and_eye(client):
    r = client.get("/api/archive").json()
    assert r["total"] == 3 and [x["number"] for x in r["rows"]] == ["12", "11", "10"]
    first = r["rows"][2]
    assert first["days"] == 7 and first["eye"] == "OD" and first["groups"] == ["Катаракта"]
    assert r["firstDate"] < r["lastDate"] and r["firstDate"].startswith("2026-04") and r["lastDate"].startswith("2026-05")


def test_filters_and_search(client):
    get = lambda **kw: [x["number"] for x in client.get("/api/archive", params=kw).json()["rows"]]  # noqa: E731
    assert get(date_from="2026-04-01", date_to="2026-04-30") == ["11", "10"]
    assert get(date_from="2026-05-01") == ["12"]                     # an open end
    assert get(date_to="2026-03-31") == []
    assert get(dx="Глаукома") == ["11"]
    assert get(outcome="без перемен") == ["11"]
    assert get(q="елкина") == ["10"]            # ё and case folded
    assert get(q="14.05.1956") == ["10"]
    assert get(q="птеригиум") == ["12"]
    assert get(q="12") == ["12"]


def test_paging_and_csv(client):
    r = client.get("/api/archive", params={"page": 9}).json()
    assert r["page"] == 1 and r["pages"] == 1          # out of range falls back to the last page
    csv = client.get("/api/archive.csv", params={"date_from": "2026-04-01", "date_to": "2026-04-30"})
    assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"]
    text = csv.content.decode("utf-8")
    assert text.startswith("﻿№ истории;") and "Ёлкина Анна Ивановна;14.05.1956" in text and "Сидорова" not in text
