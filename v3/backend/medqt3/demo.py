"""A fictional test patient for trying out diaries and printing.

    python -m medqt3.demo            # create, or recreate from scratch

Re-running removes the previous test patient with everything printed for it, so a
print test can always start from a clean sheet. Real histories are never touched.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta

from . import db as store
from . import diaries

META_KEY = "demo_patient_id"
NUMBER = "ТЕСТ"   # not a number: test patients never shift the real case numbering

# Day by day after admission: (Vis OD, status OD, Vis OS, status OS, ВГД OD, ВГД OS, OD text)
_COURSE = [
    ("0,1", "n.k. (не коррег.)", "0,6", "с коррекцией", "21", "18", "хрусталик неравномерно мутный, рефлекс с глазного дна ослаблен"),
    ("0,1", "n.k. (не коррег.)", "0,6", "с коррекцией", "20", "18", "без динамики, подготовка к операции"),
    ("0,3", "n.k. (не коррег.)", "0,6", "с коррекцией", "19", "18", "1-е сутки после ФЭК: лёгкий отёк роговицы, передняя камера средней глубины, ИОЛ в капсульном мешке"),
    ("0,4", "n.k. (не коррег.)", "0,6", "с коррекцией", "18", "18", "отёк роговицы уменьшается, ИОЛ центрирована"),
    ("0,5", "пусто", "0,6", "с коррекцией", "18", "17", "роговица прозрачная, передняя камера средней глубины, ИОЛ центрирована"),
    ("0,6", "пусто", "0,6", "с коррекцией", "17", "17", "роговица прозрачная, ИОЛ в капсульном мешке, центрирована"),
    ("0,7", "пусто", "0,6", "с коррекцией", "17", "18", "спокоен, роговица прозрачная, ИОЛ центрирована"),
    ("0,7", "пусто", "0,6", "с коррекцией", "17", "17", "спокоен, без особенностей, готов к выписке"),
]
OPERATION_DAY = 2   # the protocol is written on the morning of day 3 (index 2)

_NORM = {"Веки": "без особенностей", "Конъюнктива": "бледно-розовая", "Роговица": "прозрачная",
         "Зрачок": "круглый", "Радужка": "рисунок чёткий"}


def _exam(day: date) -> dict:
    """Primary exam in the 2.9 structured format (primary_exam_v1)."""
    local = {name: {"od_selected": [v], "od_note": "", "os_selected": [v], "os_note": ""} for name, v in _NORM.items()}
    local["Передняя камера"] = {"od_depth": "нормальная", "od_fluid": "прозрачная",
                                "os_depth": "нормальная", "os_fluid": "прозрачная"}
    local["Хрусталик"] = {"od_selected": ["неравномерно мутный"], "od_note": "", "os_selected": ["полупрозрачный"], "os_note": ""}
    local["Глазное дно"] = {"od_selected": ["не просматривается"], "od_note": "",
                            "os_selected": ["ДЗН бледно-розовый", "контуры чёткие"], "os_note": ""}
    return {
        "schema": "primary_exam_v1", "visit_date": day.isoformat(), "visit_time": "09:40",
        "complaints": "на снижение зрения правого глаза", "disease_anamnesis": "болеет около 2 лет, ухудшение за последние полгода",
        "general_state": "удовлетворительное", "bp_sys": "140", "bp_dia": "85", "hr": "74", "local": local,
        "vis_od": "0,1", "vis_os": "0,6", "vis_correction_od": "n.k. (не коррег.)", "vis_correction_os": "с коррекцией",
        "vis_od_corr": "", "vis_od_result": "", "vis_os_corr": "+1,5", "vis_os_result": "0,8", "vgd_od": "21", "vgd_os": "18",
        "diag_type": "клинический", "selected_diagnoses_od": ["Незрелая катаракта"], "selected_diagnoses_os": [],
        "selected_diagnoses_ou": [], "custom_diagnosis_od": "", "custom_diagnosis_os": "", "custom_diagnosis_ou": "",
        "selected_comorbid_diagnoses": ["Гипертоническая болезнь II ст."], "custom_comorbid_diagnosis": "",
        "selected_examinations": ["ОАК", "ОАМ", "Сахар крови", "ЭКГ", "RW"],
        "treatment": {"mydriatics": {"selected": ["Мидриацил 1%"], "note": ""}, "antibiotics": {"selected": ["Тобрекс"], "note": ""}},
    }


def remove(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (META_KEY,)).fetchone()
    if not row:
        return False
    pid = row["value"]
    cases = [r["id"] for r in conn.execute("SELECT id FROM cases WHERE patient_id = ?", (pid,))]
    with conn:
        for cid in cases:
            conn.execute("DELETE FROM print_positions WHERE record_id IN (SELECT id FROM records WHERE case_id = ?)", (cid,))
            for table in ("print_jobs", "print_state", "records", "studies", "prescriptions"):
                conn.execute(f"DELETE FROM {table} WHERE case_id = ?", (cid,))
            conn.execute("DELETE FROM cases WHERE id = ?", (cid,))
        conn.execute("DELETE FROM patients WHERE id = ?", (pid,))
        conn.execute("DELETE FROM meta WHERE key = ?", (META_KEY,))
    return True


def create(conn: sqlite3.Connection, today: date | None = None) -> str:
    """Creates the test patient and returns the case id. The last diary is yesterday's, so today's
    diary and the round can be tried too."""
    remove(conn)
    today = today or date.today()
    admitted = today - timedelta(days=len(_COURSE))
    pid, cid, ts = store.new_id(), store.new_id(), store.now_iso()
    with conn:
        conn.execute(
            "INSERT INTO patients (id, surname, name, patronymic, dob, city, street, house, created_at, updated_at)"
            " VALUES (?, 'Тестова', 'Анна', 'Ивановна', '1956-05-14', 'Тирасполь', 'ул. Тестовая', '1, кв. 1', ?, ?)",
            (pid, ts, ts))
        conn.execute(
            "INSERT INTO cases (id, patient_id, number, med_card, admitted_at, status, dx_admission, dx_clinical,"
            " dx_comorbid, created_at, updated_at) VALUES (?, ?, ?, '000000', ?, 'active', 'Незрелая катаракта OD',"
            " 'Незрелая катаракта OD', 'Гипертоническая болезнь II ст.', ?, ?)",
            (cid, pid, NUMBER, f"{admitted.isoformat()}T09:30", ts, ts))
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (META_KEY, pid))
        conn.execute(
            "INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at)"
            " VALUES (?, ?, 'primary_exam', ?, ?, ?, ?)",
            (store.new_id(), cid, f"{admitted.isoformat()}T09:40", json.dumps(_exam(admitted), ensure_ascii=False), ts, ts))

    for i, (vod, sod, vos, sos, iod, ios, od_text) in enumerate(_COURSE):
        day = admitted + timedelta(days=i)
        diaries.create(conn, cid, diaries.DiaryIn(
            date=day.isoformat(), time="09:00", bp=f"{130 + (i % 3) * 5}/80", hr="74", pulse="74",
            complaints="на снижение зрения правого глаза" if i < OPERATION_DAY else "нет",
            vis_od=vod, vis_correction_od=sod, vis_os=vos, vis_correction_os=sos,
            vis_os_corr="+1,5" if sos == "с коррекцией" else "", vis_os_result="0,8" if sos == "с коррекцией" else "",
            vgd_od=iod, vgd_os=ios, od_text=od_text, os_text="без особенностей",
            treatment="по листу назначения" if i < OPERATION_DAY else "продолжить",
        ))
        if i == OPERATION_DAY:
            with conn:
                conn.execute(
                    "INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at)"
                    " VALUES (?, ?, 'operation_protocol', ?, ?, ?, ?)",
                    (store.new_id(), cid, f"{day.isoformat()}T10:15", json.dumps({
                        "date": day.isoformat(), "time": "10:15",
                        "operation_name": "Факоэмульсификация катаракты с имплантацией ИОЛ OD",
                        "description": "Под местной анестезией. Разрез роговицы 2,2 мм. Капсулорексис. "
                                       "Факоэмульсификация ядра, аспирация хрусталиковых масс.\n"
                                       "В капсульный мешок имплантирована ИОЛ +21,5 D. Герметизация разрезов. "
                                       "Осложнений нет.",
                    }, ensure_ascii=False), ts, ts))
    return cid


def main() -> int:
    conn = store.connect()
    create(conn)
    print(f"Тестовый пациент: Тестова Анна Ивановна, история № {NUMBER} — "
          f"первичный осмотр, {len(_COURSE)} дневников и протокол операции, ничего не напечатано.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
