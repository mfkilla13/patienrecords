"""HTTP API used by the UI (desktop window now, phone later)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from html import escape

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (__version__, admission, archive, backups, clinical, diaries, dicts, discharge, dischargeprint, exams,
               prescriptions, paths, printjobs, records, rxprint, settings, stats, studies)
from . import db as store

class PrintJobIn(BaseModel):
    recordIds: list[str]
    kind: str = "sheet"             # sheet (new + reprint in place) | copy (one after another, nothing marked)
    mode: str = "continue"          # where unprinted records go: continue | new | manual
    startMm: float | None = None
    handwrittenTo: float | None = None   # «на листе есть запись от руки до N мм»
    handwrittenSheet: int | None = None  # the sheet where that handwriting ends (it may run over)


class PrintIn(BaseModel):
    printer: str


class ExtraDirIn(BaseModel):
    path: str


class DictIn(BaseModel):
    value: list | dict


class DischargePrintIn(BaseModel):
    printer: str
    copies: int = 1


class ExamIn(BaseModel):
    data: dict
    templateId: str | None = None


FRONTEND_DIST = paths.frontend_dist()
PRINTABLE_KINDS = ("primary_exam", "diary", "operation_protocol", "other")
_EYE = re.compile(r"\b(OD|OS|OU)\b")


def _age(dob: str | None, today: date) -> int | None:
    if not dob:
        return None
    y, m, d = (int(x) for x in dob.split("-"))
    return today.year - y - ((today.month, today.day) < (m, d))


def _day_of_stay(admitted_at: str | None, discharged_at: str | None, today: date) -> int | None:
    if not admitted_at:
        return None
    start = date.fromisoformat(admitted_at[:10])
    end = date.fromisoformat(discharged_at[:10]) if discharged_at else today
    return (end - start).days + 1


def _stage(status: str, operated: bool) -> str:
    if status == "discharged":
        return "discharged"
    return "post_op" if operated else "exam"


def department(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    rows = conn.execute(
        """
        SELECT c.id, c.number, c.status, c.admitted_at, c.discharged_at,
               c.dx_final, c.dx_clinical, c.dx_admission,
               p.surname, p.name, p.patronymic, p.dob,
               EXISTS (SELECT 1 FROM records r WHERE r.case_id = c.id AND r.deleted_at IS NULL
                       AND r.kind = 'operation_protocol') AS operated,
               EXISTS (SELECT 1 FROM records r WHERE r.case_id = c.id AND r.deleted_at IS NULL
                       AND r.kind = 'diary' AND substr(r.recorded_at, 1, 10) = :today) AS diary_today,
               (SELECT COUNT(*) FROM records r WHERE r.case_id = c.id AND r.deleted_at IS NULL
                       AND (r.kind IN ('primary_exam', 'diary', 'operation_protocol')
                            OR (r.kind = 'other' AND r.data_json IS NOT NULL))
                       AND r.printed_at IS NULL) AS unprinted
        FROM cases c JOIN patients p ON p.id = c.patient_id
        WHERE c.deleted_at IS NULL AND c.status IN ('active', 'discharged')
        """,
        {"today": today.isoformat()},
    ).fetchall()

    patients = []
    for r in rows:
        dx = r["dx_final"] or r["dx_clinical"] or r["dx_admission"]
        eyes = set(_EYE.findall(dx))
        # A single tag only when the diagnosis names one eye; "OD … OS …" would be misleading.
        eye = eyes.pop() if len(eyes) == 1 else None
        patients.append({
            "caseId": r["id"],
            "number": r["number"],
            "surname": r["surname"],
            "name": r["name"],
            "patronymic": r["patronymic"],
            "age": _age(r["dob"], today),
            "diagnosis": dx,
            "eye": eye,
            "admittedAt": r["admitted_at"],
            "day": _day_of_stay(r["admitted_at"], r["discharged_at"], today),
            "stage": _stage(r["status"], bool(r["operated"])),
            "diaryToday": bool(r["diary_today"]),
            "unprinted": r["unprinted"],
        })
    patients.sort(key=lambda x: (int(x["number"]) if x["number"].isdigit() else 0, x["number"]))
    return {
        "today": today.isoformat(),
        "patients": patients,
        "counts": {
            "all": len(patients),
            "noDiary": sum(1 for p in patients if not p["diaryToday"] and p["stage"] != "discharged"),
            "unprinted": sum(1 for p in patients if p["unprinted"]),
            "discharged": sum(1 for p in patients if p["stage"] == "discharged"),
        },
    }


def case_card(conn: sqlite3.Connection, case_id: str, today: date | None = None) -> dict | None:
    today = today or date.today()
    c = conn.execute(
        "SELECT c.*, p.surname, p.name, p.patronymic, p.dob, p.city, p.street, p.house"
        " FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.id = ? AND c.deleted_at IS NULL",
        (case_id,),
    ).fetchone()
    if c is None:
        return None
    rows = conn.execute(
        "SELECT * FROM records WHERE case_id = ? AND deleted_at IS NULL ORDER BY recorded_at DESC",
        (case_id,),
    ).fetchall()
    records = [clinical.record_view(r) for r in rows if r["kind"] != "passport"]
    study_rows = [studies.view(s) for s in conn.execute(
        "SELECT * FROM studies WHERE case_id = ? AND deleted_at IS NULL ORDER BY study_date DESC", (case_id,))]
    prescription_rows = [dict(p) for p in conn.execute(
        "SELECT id, category, name, method, freq, date_from, date_to FROM prescriptions"
        " WHERE case_id = ? AND deleted_at IS NULL ORDER BY date_from", (case_id,))]
    print_state = conn.execute("SELECT sheet, used_mm, last_printed_at FROM print_state WHERE case_id = ?",
                               (case_id,)).fetchone()

    latest_vision = next(({"at": r["recordedAt"], "eyes": r["vision"]} for r in records if r["vision"]), None)
    exam = next((r for r in records if r["kind"] == "primary_exam"), None)
    operations = [r for r in records if r["kind"] == "operation_protocol"]
    planned = []
    if exam:
        planned = next((s["text"].split(", ") for s in exam["sections"] if s["label"] == "План обследования"), [])
    diary_today = any(r["kind"] == "diary" and r["recordedAt"][:10] == today.isoformat() for r in records)
    dx = c["dx_final"] or c["dx_clinical"] or c["dx_admission"]

    steps = [
        {"key": "admission", "title": "Поступление", "sub": c["admitted_at"] or "", "state": "done"},
        {"key": "exam", "title": "Первичный осмотр", "sub": "заполнен" if exam else "не заполнен",
         "state": "done" if exam else "now"},
        {"key": "studies", "title": "Обследования",
         "sub": f"{len(study_rows)} из {len(planned)}" if planned else f"{len(study_rows)}",
         "state": "done" if study_rows and len(study_rows) >= len(planned) else ("now" if exam else "todo")},
        {"key": "operation", "title": "Операция",
         "sub": operations[0]["recordedAt"] if operations else "не было",
         "state": "done" if operations else "todo"},
        {"key": "diaries", "title": "Дневники",
         "sub": "сегодня написан" if diary_today else "сегодня нет",
         "state": "done" if c["status"] != "active" else ("done" if diary_today else "now")},
        {"key": "discharge", "title": "Выписка", "sub": c["discharged_at"] or "—",
         "state": "done" if c["status"] != "active" else "todo"},
    ]

    return {
        "caseId": c["id"],
        "number": c["number"],
        "medCard": c["med_card"],
        "status": c["status"],
        "outcome": c["outcome"],
        "admittedAt": c["admitted_at"],
        "dischargedAt": c["discharged_at"],
        "day": _day_of_stay(c["admitted_at"], c["discharged_at"], today),
        "patient": {
            "surname": c["surname"], "name": c["name"], "patronymic": c["patronymic"],
            "dob": c["dob"], "age": _age(c["dob"], today),
            "address": ", ".join(x for x in [c["city"], c["street"], c["house"]] if x),
        },
        "diagnosis": {"main": dx, "admission": c["dx_admission"], "clinical": c["dx_clinical"],
                      "final": c["dx_final"], "comorbid": c["dx_comorbid"]},
        "latestVision": latest_vision,
        "steps": steps,
        "records": records,
        "studies": [{"id": x["id"], "kind": x["name"], "date": x["date"], "unparsedDate": x["unparsedDate"],
                     "summary": x["result"].replace("\n", "; "), "flags": x["flags"]} for x in study_rows],
        "prescriptions": prescription_rows,
        "unprinted": sum(1 for r in records if r["printable"] and not r["printedAt"]),
        "printState": dict(print_state) if print_state else None,
    }


# Old printouts are shown in a sandboxed frame; this policy also blocks scripts and remote loads.
LEGACY_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


def create_app(db_path: Path | None = None, auto_backup: bool = False) -> FastAPI:
    db_path = Path(db_path or store.default_db_path())
    conn = store.connect(db_path)
    app = FastAPI(title="MedQT", version=__version__)
    if auto_backup:
        backups.start_daily(conn, db_path)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/department")
    def get_department():
        return department(conn)

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str):
        card = case_card(conn, case_id)
        if card is None:
            raise HTTPException(404, "История не найдена")
        return card

    def _diary_call(fn, *args):
        try:
            return fn(conn, *args)
        except diaries.DiaryError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/cases/{case_id}/diary-draft")
    def get_diary_draft(case_id: str, day: str | None = None):
        return _diary_call(diaries.draft, case_id, day or date.today().isoformat())

    @app.post("/api/cases/{case_id}/diaries", status_code=201)
    def post_diary(case_id: str, body: diaries.DiaryIn):
        return {"id": _diary_call(diaries.create, case_id, body)}

    @app.get("/api/diaries/{record_id}")
    def get_diary(record_id: str):
        return _diary_call(diaries.get, record_id)

    @app.put("/api/diaries/{record_id}")
    def put_diary(record_id: str, body: diaries.DiaryIn):
        _diary_call(diaries.update, record_id, body)
        return {"id": record_id}

    @app.get("/api/round")
    def get_round(day: str | None = None):
        day = day or date.today().isoformat()
        return {"day": day, "rows": diaries.round_rows(conn, day)}

    def _print_call(fn, *args, **kw):
        try:
            return fn(conn, *args, **kw)
        except printjobs.PrintError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/cases/{case_id}/print-plan")
    def get_print_plan(case_id: str):
        return _print_call(printjobs.plan, case_id)

    @app.post("/api/cases/{case_id}/print-jobs", status_code=201)
    def post_print_job(case_id: str, body: PrintJobIn):
        return _print_call(printjobs.create_job, case_id, body.recordIds, body.mode, body.startMm, body.kind,
                           body.handwrittenTo, body.handwrittenSheet)

    @app.get("/api/print-jobs/{job_id}/pages/{page}.png")
    def get_print_preview(job_id: str, page: int, dpi: int = 110):
        dpi = max(60, min(dpi, 220))
        return Response(_print_call(printjobs.preview_png, job_id, page, dpi), media_type="image/png")

    @app.get("/api/print-jobs/{job_id}/pdf")
    def get_print_pdf(job_id: str):
        return Response(_print_call(printjobs.pdf, job_id), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="medqt-{job_id[:8]}.pdf"'})

    @app.get("/api/printers")
    def get_printers():
        from . import winprint
        try:
            found = winprint.printers()
        except Exception as e:  # pywin32 missing or no spooler
            return {"printers": [], "default": None, "error": str(e)}
        chosen = settings.get(conn)["default_printer"]
        if chosen and chosen in found["printers"]:
            found["default"] = chosen   # the printer picked in settings wins over the Windows default
        return found

    def _call(errors, fn, *args, **kw):
        try:
            return fn(conn, *args, **kw)
        except errors as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/dictionaries")
    def get_dictionaries():
        return admission.dictionaries(conn)

    @app.get("/api/patients/search")
    def get_patient_search(q: str = ""):
        return admission.search(conn, q)

    @app.post("/api/admissions", status_code=201)
    def post_admission(body: admission.AdmissionIn):
        return _call(admission.AdmissionError, admission.admit, body)

    @app.get("/api/cases/{case_id}/exam-draft")
    def get_exam_draft(case_id: str):
        return _call(exams.ExamError, exams.draft, case_id)

    @app.post("/api/cases/{case_id}/exam", status_code=201)
    def post_exam(case_id: str, body: ExamIn):
        return _call(exams.ExamError, exams.save, case_id, body.data, None, body.templateId)

    @app.put("/api/cases/{case_id}/exam/{record_id}")
    def put_exam(case_id: str, record_id: str, body: ExamIn):
        return _call(exams.ExamError, exams.save, case_id, body.data, record_id, body.templateId)

    @app.post("/api/exam-preview", response_class=HTMLResponse)
    def post_exam_preview(body: ExamIn):
        return HTMLResponse(exams.preview_html(conn, body.data), headers={"Content-Security-Policy": LEGACY_CSP})

    @app.post("/api/exam-templates", status_code=201)
    def post_template(body: exams.TemplateIn):
        return exams.save_template(conn, body)

    @app.delete("/api/exam-templates/{template_id}")
    def delete_template(template_id: str):
        exams.delete_template(conn, template_id)
        return {"ok": True}

    def _dis(fn, *args, **kw):
        return _call(discharge.DischargeError, fn, *args, **kw)

    @app.get("/api/cases/{case_id}/discharge")
    def get_discharge(case_id: str):
        return _dis(discharge.draft, case_id)

    @app.put("/api/cases/{case_id}/discharge")
    def put_discharge(case_id: str, body: discharge.DischargeIn):
        return {"id": _dis(discharge.save, case_id, body)}

    @app.get("/api/cases/{case_id}/discharge/pdf")
    def get_discharge_pdf(case_id: str):
        return Response(_dis(dischargeprint.pdf, case_id), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="vypiska-{case_id[:8]}.pdf"'})

    @app.get("/api/cases/{case_id}/discharge/pages/{page}.png")
    def get_discharge_page(case_id: str, page: int, dpi: int = 110):
        png, count = _dis(dischargeprint.preview_png, case_id, page, max(60, min(dpi, 220)))
        return Response(png, media_type="image/png", headers={"X-Page-Count": str(count), "Cache-Control": "no-store"})

    @app.get("/api/cases/{case_id}/discharge/pages")
    def get_discharge_pages(case_id: str):
        return {"pages": _dis(dischargeprint.pages, case_id)}

    @app.post("/api/cases/{case_id}/discharge/print")
    def post_discharge_print(case_id: str, body: DischargePrintIn):
        try:
            _dis(dischargeprint.send, case_id, body.printer, body.copies)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Принтер не принял задание: {e}")
        return {"ok": True}

    @app.post("/api/cases/{case_id}/archive")
    def post_archive(case_id: str):
        _dis(discharge.archive, case_id)
        return {"ok": True}

    @app.post("/api/cases/{case_id}/unarchive")
    def post_unarchive(case_id: str):
        _dis(discharge.unarchive, case_id)
        return {"ok": True}

    @app.post("/api/cases/{case_id}/reopen")
    def post_reopen(case_id: str):
        _dis(discharge.reopen, case_id)
        return {"ok": True}

    def _st(fn, *args):
        return _call(studies.StudyError, fn, *args)

    @app.get("/api/cases/{case_id}/studies")
    def get_studies(case_id: str):
        return _st(studies.listing, case_id)

    @app.post("/api/cases/{case_id}/studies", status_code=201)
    def post_study(case_id: str, body: studies.StudyIn):
        return {"id": _st(studies.create, case_id, body)}

    @app.put("/api/studies/{study_id}")
    def put_study(study_id: str, body: studies.StudyIn):
        _st(studies.update, study_id, body)
        return {"id": study_id}

    @app.delete("/api/studies/{study_id}")
    def delete_study(study_id: str):
        _st(studies.delete, study_id)
        return {"ok": True}

    def _rx(fn, *args):
        return _call(prescriptions.PrescriptionError, fn, *args)

    @app.get("/api/cases/{case_id}/prescriptions")
    def get_prescriptions(case_id: str):
        return _rx(prescriptions.listing, case_id)

    @app.post("/api/cases/{case_id}/prescriptions", status_code=201)
    def post_prescriptions(case_id: str, body: prescriptions.PrescriptionIn):
        return {"ids": _rx(prescriptions.create, case_id, body)}

    @app.put("/api/prescriptions/{pid}")
    def put_prescription(pid: str, body: prescriptions.PrescriptionEdit):
        _rx(prescriptions.update, pid, body)
        return {"id": pid}

    @app.post("/api/prescriptions/{pid}/cancel")
    def post_prescription_cancel(pid: str, on: str | None = None):
        _rx(prescriptions.cancel, pid, on)
        return {"ok": True}

    @app.delete("/api/prescriptions/{pid}")
    def delete_prescription(pid: str):
        _rx(prescriptions.delete, pid)
        return {"ok": True}

    def _rx(fn, *args):
        try:
            return fn(conn, *args)
        except prescriptions.PrescriptionError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/cases/{case_id}/prescriptions/pdf")
    def get_prescriptions_pdf(case_id: str):
        return Response(_rx(rxprint.pdf, case_id), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="naznacheniya-{case_id[:8]}.pdf"'})

    @app.get("/api/cases/{case_id}/prescriptions/pages/{page}.png")
    def get_prescriptions_page(case_id: str, page: int, dpi: int = 110):
        png, count = _rx(rxprint.preview_png, case_id, page, max(60, min(dpi, 220)))
        return Response(png, media_type="image/png", headers={"X-Page-Count": str(count), "Cache-Control": "no-store"})

    @app.get("/api/cases/{case_id}/prescriptions/pages")
    def get_prescriptions_pages(case_id: str):
        return {"pages": _rx(rxprint.pages, case_id)}

    @app.post("/api/cases/{case_id}/prescriptions/print")
    def post_prescriptions_print(case_id: str, body: DischargePrintIn):
        try:
            _rx(rxprint.send, case_id, body.printer, body.copies)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Принтер не принял задание: {e}")
        return {"ok": True}

    @app.put("/api/prescription-templates")
    def put_prescription_templates(body: prescriptions.TemplatesIn):
        return prescriptions.save_templates(conn, body)

    def _rc(fn, *args):
        try:
            return fn(conn, *args)
        except records.RecordError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/record-options")
    def get_record_options():
        return records.options(conn)

    @app.post("/api/cases/{case_id}/records/{kind}", status_code=201)
    def post_record(case_id: str, kind: str, body: records.RecordIn):
        return _rc(records.create, case_id, kind, body)

    @app.get("/api/records/{record_id}")
    def get_record(record_id: str):
        return _rc(records.get, record_id)

    @app.put("/api/records/{record_id}")
    def put_record(record_id: str, body: records.RecordIn):
        return _rc(records.update, record_id, body)

    @app.delete("/api/records/{record_id}")
    def delete_record(record_id: str):
        _rc(records.delete, record_id)
        return {"ok": True}

    @app.post("/api/operation-templates")
    def post_operation_template(body: records.TemplateIn):
        return records.save_template(conn, body)

    @app.delete("/api/operation-templates")
    def delete_operation_template(name: str):
        return records.delete_template(conn, name)

    @app.get("/api/stats")
    def get_stats(date_from: str = "", date_to: str = ""):
        try:
            return stats.compute(conn, date_from or None, date_to or None)
        except stats.StatsError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/archive")
    def get_archive(q: str = "", period: str = "all", dx: str = "", outcome: str = "", page: int = 1):
        return archive.search(conn, q, period, dx, outcome, page)

    @app.get("/api/archive.csv")
    def get_archive_csv(q: str = "", period: str = "all", dx: str = "", outcome: str = ""):
        return Response(archive.export_csv(conn, q, period, dx, outcome), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{archive.export_name(period)}"'})

    def _bk(fn, *args):
        try:
            return fn(*args)
        except backups.BackupError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/backups")
    def get_backups():
        return backups.listing(conn, db_path)

    @app.post("/api/backups", status_code=201)
    def post_backup():
        return _bk(backups.make, conn, db_path, "manual")

    @app.post("/api/backups/{name}/restore")
    def post_restore(name: str):
        result = _bk(backups.restore, conn, db_path, name)
        printjobs.forget_cache()        # print previews were built from the data that has just been replaced
        return result

    @app.delete("/api/backups/{name}")
    def delete_backup(name: str):
        _bk(backups.delete, db_path, name)
        return {"ok": True}

    @app.put("/api/backups/extra-dir")
    def put_extra_dir(body: ExtraDirIn):
        return {"extraDir": _bk(backups.set_extra_dir, conn, body.path)}

    @app.post("/api/backups/open-folder")
    def post_open_folder():
        backups.open_folder(db_path)
        return {"ok": True}

    def _dc(fn, *args):
        try:
            return fn(conn, *args)
        except dicts.DictError as e:
            raise HTTPException(e.status, e.message)

    def _dict_info(name: str) -> dict:
        if name == "prescriptions":    # the templates of the prescription sheet, kept by their own module
            return {"name": name, "title": "Шаблоны назначений", "groups": prescriptions.CATEGORIES,
                    "hint": "Быстрый выбор на листе назначений, по разделам. Там же их можно добавлять и убирать.",
                    "value": prescriptions.templates(conn), "edited": False, "canReset": False}
        return _dc(dicts.info, name)

    @app.get("/api/dictionaries/{name}")
    def get_dictionary(name: str):
        return _dict_info(name)

    @app.put("/api/dictionaries/{name}")
    def put_dictionary(name: str, body: DictIn):
        if name == "prescriptions":
            if not isinstance(body.value, dict):
                raise HTTPException(422, "Ожидались разделы")
            prescriptions.save_templates(conn, prescriptions.TemplatesIn(templates=body.value))
        else:
            _dc(dicts.put, name, body.value)
        return _dict_info(name)

    @app.delete("/api/dictionaries/{name}")
    def delete_dictionary(name: str):
        _dc(dicts.reset, name)
        return _dict_info(name)

    @app.get("/api/settings")
    def get_settings():
        return settings.get(conn)

    @app.put("/api/settings")
    def put_settings(body: settings.SettingsIn):
        return settings.put(conn, body)

    @app.post("/api/print-jobs/{job_id}/print")
    def post_print(job_id: str, body: PrintIn):
        try:
            _print_call(printjobs.send_to_printer, job_id, body.printer)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"Принтер не принял задание: {e}")
        return {"ok": True}

    @app.post("/api/print-jobs/{job_id}/confirm")
    def post_confirm(job_id: str):
        return _print_call(printjobs.confirm, job_id)

    @app.post("/api/print-jobs/{job_id}/cancel")
    def post_cancel(job_id: str):
        _print_call(printjobs.cancel, job_id)
        return {"ok": True}

    @app.get("/api/records/{record_id}/legacy", response_class=HTMLResponse)
    def get_legacy_html(record_id: str):
        row = conn.execute("SELECT kind, html_legacy FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None or not row["html_legacy"]:
            raise HTTPException(404, "Нет сохранённого текста")
        html = row["html_legacy"]
        if row["kind"] in ("passport", "other") and "<" not in html:
            html = "<pre style='font: 14px/1.5 sans-serif; white-space: pre-wrap'>" + escape(html) + "</pre>"
        return HTMLResponse(html, headers={"Content-Security-Policy": LEGACY_CSP})

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = FRONTEND_DIST / path
            if path and file.is_file():
                return FileResponse(file)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
