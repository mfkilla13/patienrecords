"""Studies (исследования): 2.9's seven forms, their printed text, and the exam plan they fulfil.

Stored as 2.9 stored them, {"schema": "diagnostic_form_v1", "type", "fields"} for the typed
forms and {"schema": "free_text", "name", "text"} for the free one, so the 105 studies
imported from 2.9 open in the same forms. Reference ranges only highlight a value for the
doctor; they are never printed and never decide anything.
"""

from __future__ import annotations

import json
import re
import sqlite3

from pydantic import BaseModel, Field, field_validator

from . import db as store
from .importer import to_date

FREE = "Свободная форма"

# type -> [(field, label, unit, (low, high) or None, kind)]; kind "line" | "text" | "choice:<a|b|c>"
FORMS: dict[str, list[tuple]] = {
    "ОАК": [
        ("hemoglobin", "Hb", "г/л", (120, 160), "line"), ("rbc", "Эритроциты", "×10¹²/л", (3.9, 5.5), "line"),
        ("wbc", "Лейкоциты", "×10⁹/л", (4, 9), "line"), ("platelets", "Тромбоциты", "×10⁹/л", (150, 400), "line"),
        ("esr", "СОЭ", "мм/ч", (0, 20), "line"), ("color_index", "Цв. показатель", "", (0.85, 1.05), "line"),
        ("stab", "Палочкоядерные", "%", (1, 6), "line"), ("segmented", "Сегментоядерные", "%", (47, 72), "line"),
        ("eosinophils", "Эозинофилы", "%", (0.5, 5), "line"), ("lymphocytes", "Лимфоциты", "%", (19, 37), "line"),
        ("monocytes", "Моноциты", "%", (3, 11), "line"), ("note", "Примечание", "", None, "text"),
    ],
    "ОАМ": [
        ("gravity", "Уд. вес", "", (1003, 1030), "line"), ("ph", "pH", "", (5, 7), "line"),
        ("protein", "Белок", "", None, "line"), ("glucose", "Сахар", "", None, "line"),
        ("leukocytes", "Лейкоциты", "в п/з", None, "line"), ("erythrocytes", "Эритроциты", "в п/з", None, "line"),
        ("epithelium", "Эпителий", "", None, "line"), ("salts", "Соли", "", None, "line"),
        ("bacteria", "Бактерии", "", None, "line"), ("note", "Примечание", "", None, "text"),
    ],
    "Сахар крови": [("value", "Глюкоза", "ммоль/л", (3.3, 5.5), "line"), ("note", "Примечание", "", None, "text")],
    "ЭКГ": [("results", "Результаты", "", None, "text")],
    "Флюорография (ФГ)": [("number", "№ флюорографии", "", None, "line"),
                          ("result", "Результат", "", None, "choice:без патологии|норма|патология выявлена")],
    "МРС": [("result", "Результат", "", None, "choice:отрицательная|положительная|сомнительная"),
            ("titer", "Титр", "", None, "line"), ("comment", "Комментарий", "", None, "text")],
}
TYPES = ["ОАК", "ОАМ", "Сахар крови", "ЭКГ", "Флюорография (ФГ)", "МРС", FREE]

# Names in the exam plan (examinations.json) that a typed form fulfils.
PLAN_ALIASES = {"сахар крови": "Сахар крови", "rw": "МРС", "мрс": "МРС", "ренген легких": "Флюорография (ФГ)",
                "рентген легких": "Флюорография (ФГ)", "флюорография": "Флюорография (ФГ)", "фг": "Флюорография (ФГ)",
                "оак": "ОАК", "оам": "ОАМ", "экг": "ЭКГ"}


class StudyIn(BaseModel):
    date: str
    type: str
    fields: dict[str, str] = Field(default_factory=dict)
    name: str = Field("", max_length=200)       # free form only
    text: str = Field("", max_length=10000)     # free form only

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        iso = to_date(v.strip())
        if not iso:
            raise ValueError("дата исследования")
        return iso

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in TYPES:
            raise ValueError("вид исследования")
        return v


class StudyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _num(v: str) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", v or "")
    return float(m[1].replace(",", ".")) if m else None


def type_of(data: dict) -> str:
    if data.get("schema") == "diagnostic_form_v1" and data.get("type") in FORMS:
        return data["type"]
    return FREE


def results_text(data: dict) -> str:
    """The result as 2.9 showed and inserted it into the epicrisis (stationary_card._diagnostic_results_text)."""
    f = {k: _s(v) for k, v in (data.get("fields") or {}).items()}
    t = data.get("type") if data.get("schema") == "diagnostic_form_v1" else None
    join = lambda parts, sep="; ": sep.join(p for p in parts if p)  # noqa: E731
    if t == "Флюорография (ФГ)":
        return join([f"№ флюорографии: {f['number']}" if f.get("number") else "",
                     f"Результат: {f['result']}" if f.get("result") else ""], "\n")
    if t == "МРС":
        return join([f"Результат: {f['result']}" if f.get("result") else "",
                     f"Титр: {f['titer']}" if f.get("titer") else "", f.get("comment", "")], "\n")
    if t == "ОАМ":
        line1 = join([f"Уд. вес: {f['gravity']}" if f.get("gravity") else "", f"pH: {f['ph']}" if f.get("ph") else ""])
        line2 = join([f"{label}: {f[k]}" for k, label in (("protein", "Белок"), ("glucose", "Сахар"),
                      ("leukocytes", "Лейкоциты"), ("erythrocytes", "Эритроциты"), ("epithelium", "Эпителий"),
                      ("salts", "Соли"), ("bacteria", "Бактерии")) if f.get(k)])
        return join([line1, line2, f.get("note", "")], "\n")
    if t == "Сахар крови":
        return join([f"Глюкоза: {f['value']} ммоль/л" if f.get("value") else "", f.get("note", "")], "\n")
    if t == "ЭКГ":
        return f.get("results", "")
    if t == "ОАК":
        line1 = join([f"{label} {f[k]}" for k, label in (("hemoglobin", "Hb"), ("rbc", "Эр"), ("wbc", "Л"),
                      ("platelets", "Тр"), ("esr", "СОЭ")) if f.get(k)])
        line2 = join([f"{label} {f[k]}%" for k, label in (("stab", "П/я"), ("segmented", "С/я"), ("eosinophils", "Э"),
                      ("lymphocytes", "Лимф"), ("monocytes", "Мон")) if f.get(k)]
                     + ([f"ЦП {f['color_index']}"] if f.get("color_index") else []))
        return join([line1, line2, f.get("note", "")], "\n")
    return _s(data.get("text"))


def flags(data: dict) -> list[str]:
    """«СОЭ ↑», «Hb ↓» for numbers outside the reference range."""
    t = type_of(data)
    out = []
    for key, label, _unit, rng, _kind in FORMS.get(t, []):
        v = _num((data.get("fields") or {}).get(key, ""))
        if key == "gravity" and v is not None and v < 2:
            v *= 1000          # written both as «1025» and as «1,025»
        if rng and v is not None:
            if v < rng[0]:
                out.append(f"{label} ↓")
            elif v > rng[1]:
                out.append(f"{label} ↑")
    return out


def view(row: sqlite3.Row) -> dict:
    data = json.loads(row["data_json"]) if row["data_json"] else {}
    t = type_of(data)
    return {
        "id": row["id"], "date": row["study_date"], "unparsedDate": data.get("unparsed_date"),
        "type": t, "name": row["kind"] if t == FREE else t,
        "fields": {k: _s(v) for k, v in (data.get("fields") or {}).items()},
        "text": _s(data.get("text")) if t == FREE else "",
        "result": results_text(data), "flags": flags(data),
    }


def _plan_key(name: str) -> str:
    n = name.strip().lower()
    return PLAN_ALIASES.get(n, n).lower()


def _case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    c = conn.execute("SELECT id, status FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise StudyError(404, "История не найдена")
    return c


def listing(conn: sqlite3.Connection, case_id: str) -> dict:
    c = _case(conn, case_id)
    rows = conn.execute("SELECT * FROM studies WHERE case_id = ? AND deleted_at IS NULL"
                        " ORDER BY COALESCE(study_date, '') DESC, created_at DESC", (case_id,)).fetchall()
    items = [view(r) for r in rows]
    exam = conn.execute("SELECT data_json FROM records WHERE case_id = ? AND kind = 'primary_exam' AND deleted_at IS NULL"
                        " AND data_json IS NOT NULL ORDER BY recorded_at LIMIT 1", (case_id,)).fetchone()
    planned = [x for x in (json.loads(exam["data_json"]).get("selected_examinations") or []) if _s(x)] if exam else []
    done = {_plan_key(s["name"]) for s in items}
    return {
        "locked": c["status"] == "archived",
        "studies": items,
        "plan": [{"name": p, "done": _plan_key(p) in done, "type": PLAN_ALIASES.get(p.strip().lower(), "")} for p in planned],
        "forms": {t: [{"key": k, "label": lb, "unit": u, "range": list(r) if r else None, "kind": kd}
                      for k, lb, u, r, kd in fields] for t, fields in FORMS.items()},
        "types": TYPES,
    }


def _payload(d: StudyIn) -> tuple[str, dict]:
    if d.type == FREE:
        name = d.name.strip() or "Исследование"
        return name, {"schema": "free_text", "name": name, "text": d.text.strip()}
    keys = [f[0] for f in FORMS[d.type]]
    return d.type, {"schema": "diagnostic_form_v1", "type": d.type,
                    "fields": {k: _s(d.fields.get(k)) for k in keys}}


def _writable(conn: sqlite3.Connection, case_id: str) -> None:
    if _case(conn, case_id)["status"] == "archived":
        raise StudyError(409, "История в архиве — сначала верните её из архива")


def create(conn: sqlite3.Connection, case_id: str, d: StudyIn) -> str:
    _writable(conn, case_id)
    kind, data = _payload(d)
    sid, ts = store.new_id(), store.now_iso()
    with conn:
        conn.execute("INSERT INTO studies (id, case_id, kind, study_date, data_json, created_at, updated_at)"
                     " VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (sid, case_id, kind, d.date, json.dumps(data, ensure_ascii=False), ts, ts))
    return sid


def _row(conn: sqlite3.Connection, study_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM studies WHERE id = ? AND deleted_at IS NULL", (study_id,)).fetchone()
    if row is None:
        raise StudyError(404, "Исследование не найдено")
    return row


def update(conn: sqlite3.Connection, study_id: str, d: StudyIn) -> None:
    row = _row(conn, study_id)
    _writable(conn, row["case_id"])
    kind, data = _payload(d)
    with conn:   # a corrected date replaces the 2.9 typo, so the warning about it goes away
        conn.execute("UPDATE studies SET kind = ?, study_date = ?, data_json = ?, updated_at = ? WHERE id = ?",
                     (kind, d.date, json.dumps(data, ensure_ascii=False), store.now_iso(), study_id))


def delete(conn: sqlite3.Connection, study_id: str) -> None:
    row = _row(conn, study_id)
    _writable(conn, row["case_id"])
    ts = store.now_iso()
    with conn:
        conn.execute("UPDATE studies SET deleted_at = ?, updated_at = ? WHERE id = ?", (ts, ts, study_id))
