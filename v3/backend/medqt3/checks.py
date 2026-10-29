"""«Проверка данных»: entries that are almost certainly typos — mostly carried over from 2.9, where the birth date
field started at today and dates were not checked. Each found row links to the place where it is fixed; a row
the doctor confirms («Это верно») is remembered in the meta table and not shown again.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from .clinical import KIND_LABELS

OK_KEY = "checks_ok"
EXAM_KINDS = "('passport', 'discharge_summary')"     # dated by the discharge or not dated at all


def _ru(iso: str | None) -> str:
    if not iso:
        return "—"
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"


def _fio(r: sqlite3.Row) -> str:
    return " ".join(x for x in (r["surname"], r["name"], r["patronymic"]) if x)


def _confirmed(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (OK_KEY,)).fetchone()
    try:
        return set(json.loads(row["value"])) if row else set()
    except (ValueError, TypeError):
        return set()


def confirm(conn: sqlite3.Connection, check: str, item: str) -> None:
    ok = _confirmed(conn)
    ok.add(f"{check}:{item}")
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (OK_KEY, json.dumps(sorted(ok))))


# The patient's latest stay: where «Изменить данные» opens for a patient-level problem.
_LAST_CASE = ("SELECT p.id AS item, p.surname, p.name, p.patronymic, p.dob, c.id AS case_id, c.number, c.admitted_at"
              " FROM patients p JOIN cases c ON c.id = (SELECT id FROM cases WHERE patient_id = p.id AND deleted_at IS NULL"
              " ORDER BY admitted_at DESC LIMIT 1) WHERE p.deleted_at IS NULL")
_RECORD = ("SELECT r.id AS item, r.kind, r.recorded_at, c.id AS case_id, c.number, c.admitted_at,"
           " p.surname, p.name, p.patronymic FROM records r JOIN cases c ON c.id = r.case_id"
           " JOIN patients p ON p.id = c.patient_id WHERE r.deleted_at IS NULL AND c.deleted_at IS NULL"
           f" AND r.kind NOT IN {EXAM_KINDS}")
_CASE = ("SELECT c.id AS item, c.id AS case_id, c.number, c.admitted_at, c.discharged_at,"
         " p.surname, p.name, p.patronymic FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.deleted_at IS NULL")


def _record_link(r: sqlite3.Row) -> str:
    cid = r["case_id"]
    if r["kind"] == "primary_exam":
        return f"/case/{cid}/exam"
    if r["kind"] == "diary":
        return f"/case/{cid}/diary/{r['item']}"
    return f"/case/{cid}/record/{r['item']}"


def _checks(today: str) -> list[dict]:
    year = today[:4]
    oldest = f"{int(year) - 105}{today[4:]}"
    return [
        {"key": "dob_year", "title": "Год рождения — текущий или в будущем",
         "hint": "В 2.9 поле даты рождения начиналось с сегодняшней даты — год, скорее всего, не поменяли.",
         "sql": _LAST_CASE + " AND p.dob >= ? ORDER BY c.admitted_at", "args": (f"{year}-01-01",),
         "detail": lambda r: f"дата рождения {_ru(r['dob'])}", "link": lambda r: f"/case/{r['case_id']}/edit",
         "fix": "Изменить данные"},
        {"key": "dob_old", "title": "Возраст больше 105 лет",
         "hint": "Скорее всего, опечатка в годе рождения.",
         "sql": _LAST_CASE + " AND p.dob != '' AND p.dob < ? ORDER BY p.dob", "args": (oldest,),
         "detail": lambda r: f"дата рождения {_ru(r['dob'])}", "link": lambda r: f"/case/{r['case_id']}/edit",
         "fix": "Изменить данные"},
        {"key": "record_early", "title": "Запись раньше даты поступления",
         "hint": "Неверна дата записи или дата поступления.",
         "sql": _RECORD + " AND substr(r.recorded_at, 1, 10) < substr(c.admitted_at, 1, 10) ORDER BY r.recorded_at", "args": (),
         "detail": lambda r: f"{KIND_LABELS.get(r['kind'], 'Запись').lower()} от {_ru(r['recorded_at'])}, поступление {_ru(r['admitted_at'])}",
         "link": _record_link, "fix": "Открыть запись"},
        {"key": "record_future", "title": "Запись с датой позже сегодняшней",
         "hint": "Запись написана заранее или ошибка в дате.",
         "sql": _RECORD + " AND substr(r.recorded_at, 1, 10) > ? ORDER BY r.recorded_at", "args": (today,),
         "detail": lambda r: f"{KIND_LABELS.get(r['kind'], 'Запись').lower()} от {_ru(r['recorded_at'])}",
         "link": _record_link, "fix": "Открыть запись"},
        {"key": "discharge_early", "title": "Выписка раньше поступления",
         "hint": "Неверна дата выписки или дата поступления.",
         "sql": _CASE + " AND c.discharged_at != '' AND c.discharged_at < c.admitted_at ORDER BY c.admitted_at", "args": (),
         "detail": lambda r: f"поступление {_ru(r['admitted_at'])}, выписка {_ru(r['discharged_at'])}",
         "link": lambda r: f"/case/{r['case_id']}/edit", "fix": "Изменить данные"},
        {"key": "no_final_dx", "title": "Выписан без заключительного диагноза",
         "hint": "Диагноз нужен для отчёта отделения.",
         "sql": _CASE + " AND c.status != 'active' AND trim(coalesce(c.dx_final, '')) = '' ORDER BY c.discharged_at", "args": (),
         "detail": lambda r: f"выписка {_ru(r['discharged_at'])}", "link": lambda r: f"/case/{r['case_id']}/discharge",
         "fix": "Открыть выписку"},
        {"key": "no_med_card", "title": "Нет № медицинской карты (в отделении)",
         "hint": "Только у тех, кто сейчас лежит: у выписанных из 2.9 карта часто не записана.",
         "sql": _CASE + " AND c.status = 'active' AND trim(coalesce(c.med_card, '')) = '' ORDER BY c.admitted_at", "args": (),
         "detail": lambda r: f"поступление {_ru(r['admitted_at'])}", "link": lambda r: f"/case/{r['case_id']}/edit",
         "fix": "Изменить данные"},
    ]


def compute(conn: sqlite3.Connection, today: date | None = None) -> dict:
    t = (today or date.today()).isoformat()
    ok = _confirmed(conn)
    groups = []
    for ch in _checks(t):
        items = [{"item": r["item"], "caseId": r["case_id"], "number": r["number"], "fio": _fio(r),
                  "detail": ch["detail"](r), "link": ch["link"](r)}
                 for r in conn.execute(ch["sql"], ch["args"]) if f"{ch['key']}:{r['item']}" not in ok]
        groups.append({"key": ch["key"], "title": ch["title"], "hint": ch["hint"], "fix": ch["fix"], "items": items})
    return {"total": sum(len(g["items"]) for g in groups), "confirmed": len(ok), "groups": groups}


def count(conn: sqlite3.Connection, today: date | None = None) -> int:
    return compute(conn, today)["total"]
