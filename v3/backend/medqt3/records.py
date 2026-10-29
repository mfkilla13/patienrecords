"""Records added through «Новая запись»: the operation protocol and plain text records.

The protocol keeps 2.9's fields: {date, time, operation_name, description}. 2.9 saved the other
records (предоперационный эпикриз, консилиум, ...) only as HTML «Название: текст»; here the title
and the text are kept apart and the record prints on the diary sheet like the others.

Frequent operations can be saved as templates (name + description) in the meta table.
A record can be changed or removed until it is printed, like a diary.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from . import db as store
from .importer import to_date

TEXT_TITLES = ["Предоперационный эпикриз", "Консилиум", "Продление листка нетрудоспособности", "Посмертный эпикриз"]
KINDS = ("operation_protocol", "other")
TEXT_SCHEMA = "text_record_v1"
META_TEMPLATES = "operation_templates"
DEFAULT_TEMPLATES = [{
    "name": "Факоэмульсификация катаракты с имплантацией ИОЛ",
    "description": "Под местной анестезией. Разрез роговицы 2,2 мм. Капсулорексис. Гидродиссекция. "
                   "Факоэмульсификация ядра, аспирация хрусталиковых масс.\n"
                   "В капсульный мешок имплантирована ИОЛ. Герметизация разрезов. Осложнений нет.",
}]


class RecordError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class RecordIn(BaseModel):
    date: str
    time: str = ""
    title: str = Field("", max_length=300)        # operation name / the record's own title
    text: str = Field("", max_length=20000)
    # The protocol only, for the department report: the kind of operation, urgent or planned, a complication.
    op_type: str = Field("", max_length=80)
    urgency: str = Field("", max_length=10)
    complication: bool = False

    @field_validator("title", "time")
    @classmethod
    def _line(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        return "\n".join(line.rstrip() for line in v.strip().splitlines())


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    description: str = Field("", max_length=20000)


def _when(r: RecordIn) -> tuple[str, str]:
    d = to_date(r.date)
    if not d:
        raise RecordError(422, "Укажите дату")
    if d > date.today().isoformat():
        raise RecordError(422, "Дата записи не может быть позже сегодняшней")
    t = r.time.strip()
    if t and not (len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit() and int(t[:2]) < 24 and int(t[3:]) < 60):
        raise RecordError(422, "Время — в виде ЧЧ:ММ")
    return d, t


def _data(kind: str, r: RecordIn, d: str, t: str) -> dict:
    if kind == "operation_protocol":
        if not r.title and not r.text:
            raise RecordError(422, "Заполните название или описание операции")
        from .report import OP_TYPES, URGENCY, suggest_op_type
        if r.op_type and r.op_type not in OP_TYPES:
            raise RecordError(422, "Нет такого вида операции")
        if r.urgency and r.urgency not in URGENCY:
            raise RecordError(422, "Срочность — «срочно» или «планово»")
        return {"date": d, "time": t, "operation_name": r.title, "description": r.text,
                "op_type": r.op_type or suggest_op_type(r.title), "urgency": r.urgency, "complication": r.complication}
    if not r.title:
        raise RecordError(422, "Укажите, что это за запись")
    if not r.text:
        raise RecordError(422, "Запись пустая")
    return {"schema": TEXT_SCHEMA, "date": d, "time": t, "title": r.title, "text": r.text}


def _case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    c = conn.execute("SELECT id, status, admitted_at FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise RecordError(404, "История не найдена")
    if c["status"] == "archived":
        raise RecordError(409, "История в архиве — сначала верните её из архива")
    return c


def _check_date(c: sqlite3.Row, d: str) -> None:
    if c["admitted_at"] and d < c["admitted_at"][:10]:
        raise RecordError(422, "Дата записи раньше даты поступления")


def create(conn: sqlite3.Connection, case_id: str, kind: str, r: RecordIn) -> dict:
    if kind not in KINDS:
        raise RecordError(422, "Такую запись так не добавить")
    c = _case(conn, case_id)
    d, t = _when(r)
    _check_date(c, d)
    rid, ts = store.new_id(), store.now_iso()
    with conn:
        conn.execute(
            "INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (rid, case_id, kind, f"{d}T{t}" if t else d, json.dumps(_data(kind, r, d, t), ensure_ascii=False), ts, ts))
    return {"id": rid}


def _own(conn: sqlite3.Connection, record_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM records WHERE id = ? AND deleted_at IS NULL AND kind IN (?, ?)",
                       (record_id, *KINDS)).fetchone()
    if row is None:
        raise RecordError(404, "Запись не найдена")
    return row


def get(conn: sqlite3.Connection, record_id: str) -> dict:
    row = _own(conn, record_id)
    data = json.loads(row["data_json"]) if row["data_json"] else {}
    title = data.get("operation_name", "") if row["kind"] == "operation_protocol" else data.get("title", "")
    text = data.get("description", "") if row["kind"] == "operation_protocol" else data.get("text", "")
    return {"id": row["id"], "caseId": row["case_id"], "kind": row["kind"], "printedAt": row["printed_at"],
            "date": row["recorded_at"][:10], "time": row["recorded_at"][11:16], "title": title, "text": text,
            "op_type": data.get("op_type", ""), "urgency": data.get("urgency", ""),
            "complication": bool(data.get("complication")),
            "editable": bool(row["data_json"]) and not row["printed_at"]}


def update(conn: sqlite3.Connection, record_id: str, r: RecordIn) -> dict:
    row = _own(conn, record_id)
    c = _case(conn, row["case_id"])
    if row["printed_at"]:
        raise RecordError(409, "Запись уже напечатана — её нельзя менять")
    if not row["data_json"]:
        raise RecordError(409, "Запись из 2.9 без полей — её нельзя менять")
    d, t = _when(r)
    _check_date(c, d)
    old = json.loads(row["data_json"])
    data = {**old, **_data(row["kind"], r, d, t)}     # keeps anything 2.9 stored besides these fields
    with conn:
        conn.execute("UPDATE records SET recorded_at = ?, data_json = ?, updated_at = ? WHERE id = ?",
                     (f"{d}T{t}" if t else d, json.dumps(data, ensure_ascii=False), store.now_iso(), record_id))
    return {"id": record_id}


def delete(conn: sqlite3.Connection, record_id: str) -> None:
    row = _own(conn, record_id)
    _case(conn, row["case_id"])
    if row["printed_at"]:
        raise RecordError(409, "Запись уже напечатана — её нельзя удалить")
    with conn:
        conn.execute("UPDATE records SET deleted_at = ?, updated_at = ? WHERE id = ?",
                     (store.now_iso(), store.now_iso(), record_id))


def templates(conn: sqlite3.Connection) -> list[dict]:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (META_TEMPLATES,)).fetchone()
    return json.loads(row["value"]) if row else [dict(t) for t in DEFAULT_TEMPLATES]


def _save_templates(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                     (META_TEMPLATES, json.dumps(items, ensure_ascii=False)))
    return items


def save_template(conn: sqlite3.Connection, t: TemplateIn) -> list[dict]:
    """A template with the same name is replaced; a new one goes first."""
    name = " ".join(t.name.split())
    rest = [x for x in templates(conn) if x["name"].casefold() != name.casefold()]
    return _save_templates(conn, [{"name": name, "description": t.description.strip()}] + rest)


def delete_template(conn: sqlite3.Connection, name: str) -> list[dict]:
    return _save_templates(conn, [x for x in templates(conn) if x["name"] != name])


def options(conn: sqlite3.Connection) -> dict:
    from .report import OP_TYPES, URGENCY
    return {"textTitles": TEXT_TITLES, "templates": templates(conn), "now": datetime.now().strftime("%H:%M"),
            "opTypes": OP_TYPES, "urgency": list(URGENCY)}
