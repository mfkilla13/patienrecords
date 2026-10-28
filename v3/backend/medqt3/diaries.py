"""Diaries: create, edit, and the daily round.

Diary data keeps the 2.9.x JSON keys (bp, vis_od, vgd_od, od_text, ...), so old
and new diaries are read by the same code. Measurements (АД, ЧСС, пульс, Vis,
ВГД) are never copied from a previous day: they must be taken again.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from . import db as store
from .importer import to_date

TEXT_FIELDS = ("general_state", "complaints", "od_text", "os_text", "ou_text", "treatment")
MEASUREMENTS = ("bp", "hr", "pulse", "vis_od", "vis_os", "vis_correction_od", "vis_correction_os",
                "vis_od_corr", "vis_os_corr", "vis_od_result", "vis_os_result", "vgd_od", "vgd_os")


class DiaryIn(BaseModel):
    date: str
    time: str = ""
    bp: str = ""
    hr: str = ""
    pulse: str = ""
    general_state: str = "удовлетворительное"
    complaints: str = ""
    vis_od: str = ""
    vis_os: str = ""
    vis_correction_od: str = "пусто"
    vis_correction_os: str = "пусто"
    vis_od_corr: str = ""
    vis_os_corr: str = ""
    vis_od_result: str = ""
    vis_os_result: str = ""
    vgd_od: str = ""
    vgd_os: str = ""
    od_text: str = ""
    os_text: str = ""
    ou_text: str = ""
    treatment: str = ""
    discharge_note: str = ""
    basis: dict = Field(default_factory=dict)

    @field_validator("date")
    @classmethod
    def _date(cls, v: str) -> str:
        date.fromisoformat(v)
        return v

    @field_validator("time")
    @classmethod
    def _time(cls, v: str) -> str:
        v = v.strip()
        if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v


class DiaryError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _prepare(d: DiaryIn) -> tuple[str, str]:
    """recorded_at and the JSON to store; an empty time on today's diary becomes the current time."""
    if not d.time and d.date == date.today().isoformat():
        d.time = datetime.now().strftime("%H:%M")
    recorded_at = f"{d.date}T{d.time or '00:00'}"
    return recorded_at, json.dumps(d.model_dump(), ensure_ascii=False)


def _active_case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT id, status FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if row is None:
        raise DiaryError(404, "История не найдена")
    if row["status"] != "active":
        raise DiaryError(409, "История уже выписана — новые дневники не добавляются")
    return row


def create(conn: sqlite3.Connection, case_id: str, d: DiaryIn) -> str:
    _active_case(conn, case_id)
    rid, ts = store.new_id(), store.now_iso()
    recorded_at, data = _prepare(d)
    with conn:
        conn.execute(
            "INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at)"
            " VALUES (?, ?, 'diary', ?, ?, ?, ?)",
            (rid, case_id, recorded_at, data, ts, ts),
        )
    return rid


def update(conn: sqlite3.Connection, record_id: str, d: DiaryIn) -> None:
    row = conn.execute("SELECT case_id, kind, printed_at FROM records WHERE id = ? AND deleted_at IS NULL",
                       (record_id,)).fetchone()
    if row is None or row["kind"] != "diary":
        raise DiaryError(404, "Дневник не найден")
    if row["printed_at"]:
        # The paper copy already exists; changing the record would make it differ from the sheet.
        raise DiaryError(409, "Дневник уже напечатан — изменить его нельзя")
    _active_case(conn, row["case_id"])
    recorded_at, data = _prepare(d)
    with conn:
        conn.execute("UPDATE records SET data_json = ?, recorded_at = ?, updated_at = ? WHERE id = ?",
                     (data, recorded_at, store.now_iso(), record_id))


def get(conn: sqlite3.Connection, record_id: str) -> dict:
    row = conn.execute("SELECT * FROM records WHERE id = ? AND deleted_at IS NULL", (record_id,)).fetchone()
    if row is None or row["kind"] != "diary" or not row["data_json"]:
        raise DiaryError(404, "Дневник не найден")
    data = json.loads(row["data_json"])
    # 2.9 diaries store the date as "30.04.2026" (or not at all); the form needs ISO.
    data["date"] = to_date(data.get("date")) or row["recorded_at"][:10]
    data.setdefault("time", row["recorded_at"][11:16])
    return {"id": row["id"], "caseId": row["case_id"], "printedAt": row["printed_at"], "data": data}


def _diaries(conn: sqlite3.Connection, case_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, recorded_at, data_json, printed_at FROM records WHERE case_id = ? AND kind = 'diary'"
        " AND deleted_at IS NULL AND data_json IS NOT NULL ORDER BY recorded_at DESC",
        (case_id,),
    ).fetchall()


def _text_key(data: dict) -> tuple:
    return tuple((data.get(k) or "").strip() for k in ("od_text", "os_text", "ou_text"))


def draft(conn: sqlite3.Connection, case_id: str, day: str) -> dict:
    """The latest diary before `day` (to copy from) and today's diary, if already written."""
    rows = _diaries(conn, case_id)
    today = next((r for r in rows if r["recorded_at"][:10] == day), None)
    before = [r for r in rows if r["recorded_at"][:10] < day]
    previous = None
    if before:
        data = json.loads(before[0]["data_json"])
        previous = {"recordId": before[0]["id"], "date": before[0]["recorded_at"][:10], "data": data}
    same_two_days = len(before) >= 2 and _text_key(json.loads(before[0]["data_json"])) == _text_key(
        json.loads(before[1]["data_json"]))
    return {
        "previous": previous,
        "previousUnchanged": same_two_days,
        "today": {"recordId": today["id"], "printedAt": today["printed_at"], "data": json.loads(today["data_json"])}
        if today else None,
    }


def _operation_date(conn: sqlite3.Connection, case_id: str) -> str | None:
    row = conn.execute(
        "SELECT recorded_at FROM records WHERE case_id = ? AND kind = 'operation_protocol' AND deleted_at IS NULL"
        " ORDER BY recorded_at DESC LIMIT 1", (case_id,)).fetchone()
    return row["recorded_at"][:10] if row else None


def round_rows(conn: sqlite3.Connection, day: str) -> list[dict]:
    cases = conn.execute(
        "SELECT c.id, c.number, c.dx_final, c.dx_clinical, c.dx_admission, c.admitted_at,"
        " p.surname, p.name, p.patronymic FROM cases c JOIN patients p ON p.id = c.patient_id"
        " WHERE c.status = 'active' AND c.deleted_at IS NULL"
    ).fetchall()
    rows = []
    for c in cases:
        op = _operation_date(conn, c["id"])
        if op == day:
            day_label, post_op = "день операции", True
        elif op:
            n = (date.fromisoformat(day) - date.fromisoformat(op)).days
            day_label, post_op = f"день {n} после операции", True
        else:
            n = (date.fromisoformat(day) - date.fromisoformat(c["admitted_at"][:10])).days + 1 if c["admitted_at"] else None
            day_label, post_op = (f"день {n}" if n else "—"), False
        rows.append({
            "caseId": c["id"],
            "number": c["number"],
            "surname": c["surname"], "name": c["name"], "patronymic": c["patronymic"],
            "diagnosis": c["dx_final"] or c["dx_clinical"] or c["dx_admission"],
            "dayLabel": day_label,
            "postOp": post_op,
            **draft(conn, c["id"], day),
        })
    rows.sort(key=lambda r: (int(r["number"]) if r["number"].isdigit() else 0, r["number"]))
    return rows
