"""Saving primary exams and managing exam templates."""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel, Field

from . import db as store
from . import exam, settings
from .clinical import TREATMENT_LABELS
from .importer import to_date

STARTER_TEMPLATES = [
    ("Всё в норме", "", {}),
    ("Катаракта, плановая", "катаракта", {
        "complaints": "на снижение зрения",
        "disease_anamnesis": "постепенное снижение зрения в течение нескольких лет",
        "local": {"Хрусталик": {"od_selected": ["неравномерно мутный"], "od_note": ""}},
        "selected_examinations": ["ОАК", "ОАМ", "Сахар Крови", "ЭКГ", "RW"],
    }),
    ("Глаукома, плановая", "глаукома", {
        "complaints": "на снижение зрения, периодический зрительный дискомфорт",
        "disease_anamnesis": "наблюдается по поводу глаукомы, получает гипотензивные капли",
        "local": {"Глазное дно": {"od_selected": ["ДЗН бледный", "экскавация глаукоматозная"], "od_note": ""}},
        "selected_examinations": ["ОАК", "ОАМ", "Сахар Крови", "ЭКГ", "RW", "Суточное ВГД"],
    }),
]


class ExamError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    keywords: str = Field("", max_length=200)
    data: dict


def _case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    c = conn.execute("SELECT * FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise ExamError(404, "История не найдена")
    return c


def _seed_templates(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM exam_templates").fetchone()[0]:
        return
    ts = store.now_iso()
    with conn:
        for name, keywords, extra in STARTER_TEMPLATES:
            data = exam.normal_exam()
            for k, v in extra.items():
                if k == "local":
                    for row, cell in v.items():
                        data["local"][row].update(cell)
                else:
                    data[k] = v
            conn.execute("INSERT INTO exam_templates (id, name, keywords, data_json, created_at, updated_at)"
                         " VALUES (?,?,?,?,?,?)", (store.new_id(), name, keywords, exam.dumps(exam.template_part(data)), ts, ts))


def templates(conn: sqlite3.Connection, diagnosis: str = "") -> list[dict]:
    _seed_templates(conn)
    rows = conn.execute("SELECT * FROM exam_templates WHERE deleted_at IS NULL ORDER BY use_count DESC, name").fetchall()
    out = [{"id": r["id"], "name": r["name"], "keywords": r["keywords"], "useCount": r["use_count"],
            "suggested": bool(r["keywords"]) and exam.matches(r["keywords"], diagnosis),
            # Without measurement and diagnosis keys: applying a template must not wipe what was entered.
            "data": exam.template_part(json.loads(r["data_json"]))} for r in rows]
    if not any(t["suggested"] for t in out):
        for t in out:
            if t["name"] == "Всё в норме":
                t["suggested"] = True
    return out


def save_template(conn: sqlite3.Connection, t: TemplateIn) -> dict:
    ts, tid = store.now_iso(), store.new_id()
    with conn:
        conn.execute("INSERT INTO exam_templates (id, name, keywords, data_json, created_at, updated_at)"
                     " VALUES (?,?,?,?,?,?)", (tid, t.name.strip(), t.keywords.strip(), exam.dumps(exam.template_part(t.data)), ts, ts))
    return {"id": tid}


def delete_template(conn: sqlite3.Connection, tid: str) -> None:
    with conn:
        conn.execute("UPDATE exam_templates SET deleted_at = ?, updated_at = ? WHERE id = ?", (store.now_iso(), store.now_iso(), tid))


def draft(conn: sqlite3.Connection, case_id: str) -> dict:
    """Everything the quick exam screen needs for one case."""
    c = _case(conn, case_id)
    existing = conn.execute("SELECT * FROM records WHERE case_id = ? AND kind = 'primary_exam' AND deleted_at IS NULL"
                            " ORDER BY recorded_at LIMIT 1", (case_id,)).fetchone()
    previous = conn.execute(
        "SELECT r.data_json, r.recorded_at, c2.number FROM records r JOIN cases c2 ON c2.id = r.case_id"
        " WHERE c2.patient_id = ? AND c2.id != ? AND r.kind = 'primary_exam' AND r.data_json IS NOT NULL"
        " AND r.deleted_at IS NULL ORDER BY r.recorded_at DESC LIMIT 1", (c["patient_id"], case_id)).fetchone()
    dx = c["dx_clinical"] or c["dx_admission"]
    return {
        "case": {"id": c["id"], "number": c["number"], "status": c["status"], "admittedAt": c["admitted_at"],
                 "dxAdmission": c["dx_admission"], "dxClinical": c["dx_clinical"], "dxComorbid": c["dx_comorbid"]},
        "existing": {"id": existing["id"], "printedAt": existing["printed_at"],
                     "data": exam.complete(json.loads(existing["data_json"])) if existing["data_json"] else None,
                     "legacyOnly": not existing["data_json"]} if existing else None,
        "previous": {"number": previous["number"], "date": previous["recorded_at"][:10],
                     "data": exam.template_part(json.loads(previous["data_json"]))} if previous else None,
        "prefill": exam.admission_prefill(dict(c)),
        "templates": templates(conn, dx or ""),
        "options": {
            "local": exam.LOCAL_OPTIONS, "anterior": exam.ANTERIOR_OPTIONS, "anteriorRow": exam.ANTERIOR,
            "norms": exam.NORMS, "anteriorNorm": exam.ANTERIOR_NORM, "objective": exam.OBJECTIVE,
            "allergy": exam.ALLERGY, "insurance": exam.INSURANCE, "diagTypes": exam.DIAG_TYPES,
            "complaintWords": exam.COMPLAINT_WORDS, "treatmentLabels": TREATMENT_LABELS,
        },
        "base": exam.normal_exam(),
    }


def save(conn: sqlite3.Connection, case_id: str, data: dict, record_id: str | None = None,
         template_id: str | None = None) -> dict:
    c = _case(conn, case_id)
    if c["status"] != "active":
        raise ExamError(409, "История выписана — осмотр только для чтения")
    data = exam.apply_fundus_rule(exam.complete(data))
    visit = to_date(data.get("visit_date")) or (c["admitted_at"] or "")[:10]
    if not visit:
        raise ExamError(422, "Укажите дату осмотра")
    data["visit_date"] = visit
    time = (data.get("visit_time") or "").strip()
    recorded_at = f"{visit}T{time}" if time else visit
    html = exam.render_html(data, settings.get(conn)["doctor_signature"])
    ts = store.now_iso()
    dx, comorbid = exam.diagnosis_text(data), exam.comorbid_text(data)
    with conn:
        if record_id:
            r = conn.execute("SELECT case_id, kind, printed_at FROM records WHERE id = ?", (record_id,)).fetchone()
            if r is None or r["case_id"] != case_id or r["kind"] != "primary_exam":
                raise ExamError(404, "Осмотр не найден")
            if r["printed_at"]:
                raise ExamError(409, "Осмотр уже напечатан — изменить его нельзя, чтобы он не разошёлся с бумагой")
            conn.execute("UPDATE records SET data_json = ?, html_legacy = ?, recorded_at = ?, updated_at = ? WHERE id = ?",
                         (exam.dumps(data), html, recorded_at, ts, record_id))
        else:
            if conn.execute("SELECT 1 FROM records WHERE case_id = ? AND kind = 'primary_exam' AND deleted_at IS NULL",
                            (case_id,)).fetchone():
                raise ExamError(409, "Первичный осмотр в этой истории уже есть — откройте его")
            record_id = store.new_id()
            conn.execute("INSERT INTO records (id, case_id, kind, recorded_at, data_json, html_legacy, created_at, updated_at)"
                         " VALUES (?, ?, 'primary_exam', ?, ?, ?, ?, ?)",
                         (record_id, case_id, recorded_at, exam.dumps(data), html, ts, ts))
        # Like 2.9: a clinical diagnosis goes to the clinical field, a preliminary one to the admission field.
        column = "dx_clinical" if data["diag_type"] == "клинический" else "dx_admission"
        if dx:
            conn.execute(f"UPDATE cases SET {column} = ?, updated_at = ? WHERE id = ?", (dx, ts, case_id))
        if comorbid:
            conn.execute("UPDATE cases SET dx_comorbid = ?, updated_at = ? WHERE id = ?", (comorbid, ts, case_id))
        if template_id:
            conn.execute("UPDATE exam_templates SET use_count = use_count + 1 WHERE id = ?", (template_id,))
    return {"id": record_id}


def preview_html(conn: sqlite3.Connection, data: dict) -> str:
    return exam.render_html(exam.apply_fundus_rule(exam.complete(data)), settings.get(conn)["doctor_signature"])
