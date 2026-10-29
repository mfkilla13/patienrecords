import io
import re
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import report, reportdoc
from medqt3.api import create_app


def add(conn, n, admitted, discharged=None, *, status="archived", outcome="улучшение", dx="Глаукома OD", group="",
        city="Бендеры", dob="1950-01-01", channel="", residence=""):
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO patients (id, surname, name, dob, city, residence, created_at, updated_at)"
                     " VALUES (?, 'Т', 'А', ?, ?, ?, ?, ?)", (f"p{n}", dob, city, residence, ts, ts))
        conn.execute("INSERT INTO cases (id, patient_id, number, admitted_at, discharged_at, status, outcome, dx_final,"
                     " report_group, admission_channel, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"c{n}", f"p{n}", str(n), admitted, discharged, status, outcome, dx, group, channel, ts, ts))


@pytest.fixture()
def env(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    return TestClient(create_app(path)), conn


def test_main_indicators_structure_and_operations(env):
    client, conn = env
    add(conn, 1, "2026-01-10T09:00", "2026-01-19", dx="Острый приступ глаукомы OS. Незрелая катаракта OU",
        city="Гиска", channel="самообращение")                                                   # 10 bed-days
    add(conn, 2, "2026-02-01T09:00", "2026-02-05", dx="Халязион верхнего века OD", group="Заболевания век и слезного аппарата",
        dob="2012-05-01", channel="направлен профильным специалистом КП", residence="иногородний")  # 5, a child
    add(conn, 3, "2026-03-01T09:00", "2026-03-06", dx="Кератит OD", outcome="с выздоровлением")      # 6
    add(conn, 4, "2026-06-25T09:00", None, status="active", dx="Увеит OS")                          # still in
    add(conn, 5, "2025-03-01T09:00", "2025-03-04", dx="Глаукома")                                  # last year, 4
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at) VALUES"
                     " ('r1', 'c2', 'operation_protocol', '2026-02-02T10:00', ?, ?, ?)",
                     ('{"operation_name": "Удаление халязиона верхнего века", "urgency": "планово", "complication": true}', ts, ts))
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('bed_days_plan', '365')")

    r = client.get("/api/report?date_from=2026-01-01&date_to=2026-06-30").json()
    m = r["current"]["main"]
    assert (m["treated"], m["admitted"], m["discharged"], m["bedDays"]) == (3, 4, 3, 21)
    assert m["avgStay"] == 7.0 and m["turnover"] == 0.15 and m["bedWork"] == 1.05
    assert (m["rural"], m["nonresident"], m["children"], m["teens"]) == (1, 1, 1, 0)
    assert m["planPercent"] == round(21 / (365 * 181 / 365) * 100, 2)
    assert (m["emergency"], m["planned"], m["channelUnknown"]) == (1, 1, 2)
    rows = {x["label"]: x for x in r["current"]["structure"]}
    assert rows["Глаукома"]["count"] == 1 and rows["Заболевания век и слезного аппарата"]["bedDays"] == 5
    assert rows["Кератиты"]["share"] == 33.33
    assert [a["number"] for a in r["current"]["autoGroups"]] == ["1", "3"]       # suggested, not chosen
    ops = {x["label"]: x for x in r["current"]["operations"]}
    assert ops["Операции на веках"]["count"] == 1 and ops["Операции на веках"]["bedDays"] == 5
    s = r["current"]["surgery"]
    assert (s["operations"], s["planned"], s["operatedPlanned"], s["complicationsPlanned"]) == (1, 1, 1, 1)
    assert {o["label"]: o["count"] for o in r["current"]["outcomes"]} == {"С улучшением": 2, "С выздоровлением": 1}
    assert r["previous"]["hasData"] and r["previous"]["main"]["bedDays"] == 4
    assert r["title"] == "1 полугодие 2026 г."

    assert client.put("/api/cases/c3/report-group", json={"group": "Увеиты"}).status_code == 200
    assert client.put("/api/cases/c3/report-group", json={"group": "Нет такой"}).status_code == 422
    rows = {x["label"]: x for x in client.get("/api/report?date_from=2026-01-01&date_to=2026-06-30").json()["current"]["structure"]}
    assert rows["Увеиты"]["count"] == 1 and rows["Кератиты"]["count"] == 0


def test_word_file_opens_and_has_the_tables(env):
    client, conn = env
    add(conn, 1, "2026-01-10T09:00", "2026-01-19")
    res = client.get("/api/report.docx?date_from=2026-01-01&date_to=2026-12-31")
    assert res.status_code == 200 and "filename*=UTF-8''" in res.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(res.content))
    xml = z.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml)
    for s in ("Отчёт офтальмологического отделения за 2026 год", "Основные показатели работы отделения",
              "Структура пролеченных больных за 2025-2026 годы", "Операции за 2026 год", "Глаукома", "Итого:"):
        assert s in text, s
    assert z.testzip() is None and xml.count("<w:tbl>") == 3


def test_suggestions_and_titles():
    assert report.suggest_group("Незрелая катаракта OD. Острый приступ терминальной глауком") == "Глаукома"
    assert report.suggest_group("Гемофтальм OD. Пролиферативная диабетическая ретинопатия OS") == "Диабетические ретинопатии"
    assert report.suggest_group("Острая нейрооптикопатия OD. Диструкция стекловидного тела") == "Заболевания зрительного нерва"
    assert report.suggest_group("Абсцедирующий ячмень нижнего века OD") == "Заболевания век и слезного аппарата"
    assert report.suggest_group("Высокая осложненная близорукость OU") == "Высокая осложнённая близорукость"
    assert report.suggest_group("") == "Другие заболевания глаза"
    assert report.suggest_op_type("Факоэмульсификация катаракты") == "Экстракция катаракты"
    assert report.suggest_op_type("Иссечение халязиона") == "Операции на веках"
    assert reportdoc.period_title("2026-07-01", "2026-09-30") == "3 квартал 2026 г."
    assert reportdoc.period_title("2026-10-01", "2026-10-31") == "октябрь 2026 г."
    assert reportdoc.period_title("2026-10-03", "2026-10-31").startswith("период с 03.10.2026")


def test_old_database_gets_the_new_columns(tmp_path):
    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE patients (id TEXT PRIMARY KEY, surname TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',"
                    " patronymic TEXT NOT NULL DEFAULT '', dob TEXT, city TEXT NOT NULL DEFAULT '', street TEXT NOT NULL DEFAULT '',"
                    " house TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,"
                    " legacy_id INTEGER UNIQUE); PRAGMA user_version = 1;")
    c.close()
    conn = store.connect(path)
    assert "residence" in {r[1] for r in conn.execute("PRAGMA table_info(patients)")}
    assert {"report_group", "admission_channel"} <= {r[1] for r in conn.execute("PRAGMA table_info(cases)")}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == store.SCHEMA_VERSION


def test_admission_channel_and_protocol_kind(env):
    client, conn = env
    body = {"surname": "Образцова", "admittedDate": "2026-10-01", "dxAdmission": "Глаукома OS",
            "channel": "доставлен СМП", "residence": "иностранный гражданин"}
    cid = client.post("/api/admissions", json=body).json()["caseId"]
    row = conn.execute("SELECT c.admission_channel, p.residence FROM cases c JOIN patients p ON p.id = c.patient_id"
                       " WHERE c.id = ?", (cid,)).fetchone()
    assert tuple(row) == ("доставлен СМП", "иностранный гражданин")
    assert client.post("/api/admissions", json={**body, "surname": "Другая", "channel": "пешком"}).status_code == 422
    rid = client.post(f"/api/cases/{cid}/records/operation_protocol",
                      json={"date": "2026-10-02", "title": "Синустрабекулэктомия OS", "text": "", "urgency": "планово"}).json()["id"]
    got = client.get(f"/api/records/{rid}").json()
    assert (got["op_type"], got["urgency"], got["complication"]) == ("Антиглаукоматозные операции", "планово", False)
    assert client.get(f"/api/cases/{cid}/discharge").json()["form"]["report_group"] == "Глаукома"


def test_department_summary(env):
    client, conn = env
    from datetime import date, timedelta
    today = date.today()
    add(conn, 1, f"{today}T09:00", None, status="active")
    add(conn, 2, f"{today - timedelta(days=5)}T09:00", None, status="active")
    add(conn, 3, f"{today - timedelta(days=9)}T09:00", f"{today}", status="discharged")
    add(conn, 4, f"{today.replace(day=1) - timedelta(days=20)}T09:00", f"{today.replace(day=1) - timedelta(days=2)}")  # last month
    s = client.get("/api/department").json()["summary"]
    assert s == {"beds": 20, "occupied": 2, "admittedToday": 1, "dischargedToday": 1,
                 "dischargedMonth": 1, "issues": s["issues"]}
