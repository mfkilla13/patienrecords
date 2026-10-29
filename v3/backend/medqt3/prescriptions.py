"""Prescriptions (лист назначений): 2.9's four categories with their templates, method, frequency, dates.

2.9 kept the templates only while its window was open; here they live in the meta table.
2.9 also filled «Дата отмены» with today's date by default — here it stays empty until
the doctor cancels the prescription.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from pydantic import BaseModel, Field, field_validator

from . import db as store
from .importer import to_date

CATEGORIES = {"stol": "Стол, режим", "exam": "Обследования", "drugs": "Препараты", "lfk": "ЛФК, массаж"}
# Categories without method and frequency (2.9 hid those fields for them).
PLAIN = ("stol", "exam", "lfk")

DEFAULT_TEMPLATES = {
    "stol": ["стол 15", "стол 9", "стол 14", "режим общий", "режим постельный"],
    "exam": ["Общий анализ мочи", "Биохимический анализ крови", "Флюорография", "Маммография", "ЭКГ",
             "УЗИ органов брюшной полости", "Рентген грудной клетки", "Анализ кала"],
    "drugs": ["анальгетики", "антибиотикотерапия", "физиолечение", "спазмолитики", "витамины"],
    "lfk": ["ЛФК", "массаж", "лечебная физкультура"],
}
METHODS = ["в/в", "в/м", "перорально", "местно", "п/б"]
FREQS = ["1 раз в сутки", "2 раза в сутки", "3 раза в сутки", "4 раза в сутки"]
META_KEY = "prescription_templates"


def _date(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    iso = to_date(v.strip())
    if not iso:
        raise ValueError("дата")
    return iso


class PrescriptionIn(BaseModel):
    category: str
    names: list[str] = Field(min_length=1)
    method: str = Field("", max_length=100)
    freq: str = Field("", max_length=100)
    date_from: str | None = None
    date_to: str | None = None

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError("категория")
        return v

    @field_validator("names")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        names = [n.strip() for n in v if n.strip()]
        if not names:
            raise ValueError("назначение")
        return names

    @field_validator("date_from", "date_to")
    @classmethod
    def _dates(cls, v: str | None) -> str | None:
        return _date(v)


class PrescriptionEdit(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    method: str = Field("", max_length=100)
    freq: str = Field("", max_length=100)
    date_from: str | None = None
    date_to: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def _dates(cls, v: str | None) -> str | None:
        return _date(v)


class TemplatesIn(BaseModel):
    templates: dict[str, list[str]]


class PrescriptionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def templates(conn: sqlite3.Connection) -> dict[str, list[str]]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (META_KEY,)).fetchone()
    saved = json.loads(row["value"]) if row else {}
    return {k: list(saved.get(k, DEFAULT_TEMPLATES[k])) for k in CATEGORIES}


def save_templates(conn: sqlite3.Connection, t: TemplatesIn) -> dict[str, list[str]]:
    clean = {k: list(dict.fromkeys(x.strip() for x in t.templates.get(k, []) if x.strip())) for k in CATEGORIES}
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (META_KEY, json.dumps(clean, ensure_ascii=False)))
    return clean


def _case(conn: sqlite3.Connection, case_id: str, write: bool = False) -> sqlite3.Row:
    c = conn.execute("SELECT id, status FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise PrescriptionError(404, "История не найдена")
    if write and c["status"] == "archived":
        raise PrescriptionError(409, "История в архиве — сначала верните её из архива")
    return c


def view(row: sqlite3.Row, today: str) -> dict:
    return {"id": row["id"], "category": row["category"], "name": row["name"], "method": row["method"],
            "freq": row["freq"], "dateFrom": row["date_from"], "dateTo": row["date_to"],
            "active": not row["date_to"] or row["date_to"] > today}   # cancelled on that day


def listing(conn: sqlite3.Connection, case_id: str) -> dict:
    c = _case(conn, case_id)
    today = date.today().isoformat()
    rows = conn.execute("SELECT * FROM prescriptions WHERE case_id = ? AND deleted_at IS NULL"
                        " ORDER BY COALESCE(date_from, ''), created_at", (case_id,)).fetchall()
    return {"locked": c["status"] == "archived", "items": [view(r, today) for r in rows],
            "categories": CATEGORIES, "plain": list(PLAIN), "templates": templates(conn),
            "methods": METHODS, "freqs": FREQS}


def create(conn: sqlite3.Connection, case_id: str, p: PrescriptionIn) -> list[str]:
    _case(conn, case_id, write=True)
    ts = store.now_iso()
    method, freq = ("", "") if p.category in PLAIN else (p.method.strip(), p.freq.strip())
    ids = []
    with conn:
        for name in p.names:
            pid = store.new_id()
            ids.append(pid)
            conn.execute("INSERT INTO prescriptions (id, case_id, category, name, method, freq, date_from, date_to,"
                         " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (pid, case_id, p.category, name, method, freq, p.date_from or date.today().isoformat(),
                          p.date_to, ts, ts))
    return ids


def _row(conn: sqlite3.Connection, pid: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM prescriptions WHERE id = ? AND deleted_at IS NULL", (pid,)).fetchone()
    if row is None:
        raise PrescriptionError(404, "Назначение не найдено")
    _case(conn, row["case_id"], write=True)
    return row


def update(conn: sqlite3.Connection, pid: str, p: PrescriptionEdit) -> None:
    _row(conn, pid)
    with conn:
        conn.execute("UPDATE prescriptions SET name = ?, method = ?, freq = ?, date_from = ?, date_to = ?, updated_at = ?"
                     " WHERE id = ?", (p.name.strip(), p.method.strip(), p.freq.strip(), p.date_from, p.date_to,
                                       store.now_iso(), pid))


def cancel(conn: sqlite3.Connection, pid: str, on: str | None = None) -> None:
    """«Отменить» — the cancel date is today unless the doctor gives another one."""
    _row(conn, pid)
    with conn:
        conn.execute("UPDATE prescriptions SET date_to = ?, updated_at = ? WHERE id = ?",
                     (_date(on) or date.today().isoformat(), store.now_iso(), pid))


def delete(conn: sqlite3.Connection, pid: str) -> None:
    _row(conn, pid)
    ts = store.now_iso()
    with conn:
        conn.execute("UPDATE prescriptions SET deleted_at = ?, updated_at = ? WHERE id = ?", (ts, ts, pid))
