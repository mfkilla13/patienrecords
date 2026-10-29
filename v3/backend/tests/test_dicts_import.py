import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import importer
from medqt3.api import create_app

# The tables of a 2.9 patients.db, with the columns the move reads. All data here is made up.
LEGACY_SCHEMA = """
CREATE TABLE patients (id INTEGER PRIMARY KEY, surname TEXT, name TEXT, patronymic TEXT, dob TEXT, city TEXT,
    street TEXT, house TEXT, apartment TEXT, created_at TEXT);
CREATE TABLE medical_cases (id INTEGER PRIMARY KEY, patient_id INTEGER, card_number TEXT, admission_date TEXT,
    admission_time TEXT, discharge_date TEXT, discharge_time TEXT, outcome TEXT, status TEXT, final_diagnosis TEXT,
    discharge_summary TEXT, recommendations TEXT, created_at TEXT, closed_at TEXT, medical_record_number TEXT);
CREATE TABLE histories (id INTEGER PRIMARY KEY, patient_id INTEGER, visit_date TEXT, record_type TEXT, examination TEXT,
    diagnosis TEXT, treatment TEXT, notes TEXT, diag_admission TEXT, diag_clinical TEXT, diag_comorbid TEXT,
    history_id INTEGER, printed INTEGER, printed_at TEXT, print_batch_id TEXT, print_top_offset_mm REAL);
CREATE TABLE diagnostics (id INTEGER PRIMARY KEY, patient_id INTEGER, history_id INTEGER, study_date TEXT, name TEXT,
    results TEXT, created_at TEXT);
CREATE TABLE appointments (id INTEGER PRIMARY KEY, history_id INTEGER, name TEXT, method TEXT, freq TEXT,
    date_assign TEXT, date_cancel TEXT, created_at TEXT);
CREATE TABLE case_print_state (case_id INTEGER PRIMARY KEY, diary_current_page_used_mm REAL,
    diary_last_printed_at TEXT, diary_last_batch_id TEXT);
"""


def legacy_db(path, patients=2, orphan=False):
    c = sqlite3.connect(path)
    c.executescript(LEGACY_SCHEMA)
    for i in range(1, patients + 1):
        c.execute("INSERT INTO patients VALUES (?, ?, 'Мария', 'Петровна', '01.02.1950', 'Бендеры', '', '5', '', '2026-03-01')",
                  (i, f"Образцова{i}"))
        c.execute("INSERT INTO medical_cases (id, patient_id, card_number, admission_date, admission_time, status, created_at)"
                  " VALUES (?, ?, ?, ?, '09:30', ?, '2026-03-01')", (i, i, str(100 + i), f"0{i}.03.2026", "active" if i == patients else "archived"))
        c.execute("INSERT INTO histories (id, patient_id, visit_date, record_type, examination, history_id, notes)"
                  " VALUES (?, ?, ?, 'diary', '<p>Жалоб нет</p>', ?, '')", (i, i, f"2026-03-0{i}T10:00:00", i))
        c.execute("INSERT INTO diagnostics VALUES (?, ?, ?, '02.03.2026', 'ЭКГ', 'Ритм синусовый', '2026-03-02')", (i, i, i))
        c.execute("INSERT INTO appointments VALUES (?, ?, 'Тауфон', 'капли', '3 р/д', '02.03.2026', '', '2026-03-02')", (i, i))
    if orphan:   # a record of a case that 2.9 no longer has
        c.execute("INSERT INTO histories (id, patient_id, visit_date, record_type, history_id) VALUES (99, 1, '2026-03-05', 'diary', 77)")
    c.commit()
    c.close()
    return path


@pytest.fixture()
def setup(tmp_path):
    path = tmp_path / "data" / "medqt.db"
    conn = store.connect(path)
    return TestClient(create_app(path)), conn, path


def test_import_counts_skip_orphans_and_add_29_dictionaries(tmp_path, capsys):
    old = legacy_db(tmp_path / "patients.db", 2, orphan=True)
    data29 = tmp_path / "data29"
    data29.mkdir()
    (data29 / "examinations.json").write_text(json.dumps(["ОАК", "Гониоскопия"], ensure_ascii=False), encoding="utf-8")
    target = tmp_path / "new" / "medqt.db"
    assert importer.main([str(old), "--db", str(target), "--dicts", str(data29)]) == 2     # the orphan shows
    out = capsys.readouterr().out
    assert "records        было    3  стало    2  РАСХОЖДЕНИЕ" in out and "patients       было    2  стало    2  ok" in out
    assert "«Обследования»: добавлено 1" in out
    conn = store.connect(target)
    client = TestClient(create_app(target))
    exams = client.get("/api/dictionaries").json()["examinations"]
    assert exams[-1] == "Гониоскопия" and exams.count("ОАК") == 1
    assert len(client.get("/api/department").json()["patients"]) == 1
    assert conn.execute("SELECT COUNT(*) FROM prescriptions").fetchone()[0] == 2


def test_dictionary_edit_and_reset(setup):
    client, conn, path = setup
    r = client.put("/api/dictionaries/examinations", json={"value": [" ОАК ", "ЭКГ", "", "оак", "Гониоскопия"]}).json()
    assert r["value"] == ["ОАК", "ЭКГ", "Гониоскопия"] and r["edited"]
    assert client.get("/api/dictionaries").json()["examinations"] == ["ОАК", "ЭКГ", "Гониоскопия"]
    assert client.put("/api/dictionaries/nope", json={"value": []}).status_code == 404
    assert client.put("/api/dictionaries/examinations", json={"value": {"a": 1}}).status_code == 422
    t = client.put("/api/dictionaries/treatment", json={"value": {"metabolism": ["Тауфон"], "unknown": ["x"]}}).json()["value"]
    assert t["metabolism"] == ["Тауфон"] and "unknown" not in t and "antibiotics" in t
    r = client.delete("/api/dictionaries/examinations").json()
    assert not r["edited"] and "RW" in r["value"]
    assert client.get("/api/dictionaries/treatment").json()["groups"]["metabolism"] == "Для улучшения обмена веществ"

    rx = client.get("/api/dictionaries/prescriptions").json()
    assert rx["groups"]["drugs"] == "Препараты" and not rx["canReset"]
    rx = client.put("/api/dictionaries/prescriptions", json={"value": {**rx["value"], "lfk": ["ЛФК", "Массаж воротниковой зоны"]}}).json()
    assert rx["value"]["lfk"] == ["ЛФК", "Массаж воротниковой зоны"]
