"""Discharge (выписка): the 2.9 discharge form, its auto-filled parts, archive and reopen.

The saved form keeps 2.9's payload keys (epicrisis, vis_od, vgd_od_max, tono_od_ro,
discharge_local, ...) plus the fields 2.9 kept only inside its summary HTML
(destination, workplace), so discharges imported from 2.9 open and print the same way.
One discharge_summary record per case; the case row carries status, dates, outcome,
the final diagnosis and the recommendations, as in 2.9.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from html import unescape

from pydantic import BaseModel, Field, field_validator

from . import clinical
from . import studies as studies_mod
from . import db as store
from . import exam as exam_mod
from .importer import to_date

OUTCOMES = ["улучшение", "выздоровление", "без перемен", "ухудшение", "перевод", "самовольно покинул", "смерть", "другое"]

VISION_KEYS = ("vis_od", "vis_os", "vis_correction_od", "vis_correction_os", "vis_od_corr", "vis_os_corr",
               "vis_od_result", "vis_os_result", "vgd_od", "vgd_os")
EXTRA_KEYS = ("vgd_od_max", "vgd_od_min", "vgd_os_max", "vgd_os_min", "elasto_od", "elasto_os",
              *(f"tono_{e}_{k}" for e in ("od", "os") for k in ("ro", "c", "kb", "f")))


class DischargeIn(BaseModel):
    discharge_date: str
    discharge_time: str = ""
    destination: str = Field("", max_length=300)
    workplace: str = Field("", max_length=300)
    outcome: str = Field("", max_length=80)
    final_diagnosis: str = Field("", max_length=2000)
    report_group: str = Field("", max_length=120)     # the row of the department report; kept on the case
    epicrisis: str = Field("", max_length=20000)
    recommendations: str = Field("", max_length=10000)
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
    vgd_od_max: str = ""
    vgd_od_min: str = ""
    vgd_os_max: str = ""
    vgd_os_min: str = ""
    elasto_od: str = ""
    elasto_os: str = ""
    tono_od_ro: str = ""
    tono_od_c: str = ""
    tono_od_kb: str = ""
    tono_od_f: str = ""
    tono_os_ro: str = ""
    tono_os_c: str = ""
    tono_os_kb: str = ""
    tono_os_f: str = ""
    treatment_summary: str = Field("", max_length=5000)
    sig_dep_chief: bool = False
    sig_chief: bool = False
    discharge_local: dict = Field(default_factory=dict)

    @field_validator("discharge_date")
    @classmethod
    def _date(cls, v: str) -> str:
        iso = to_date(v.strip())
        if not iso:
            raise ValueError("дата выписки")
        return iso

    @field_validator("discharge_time")
    @classmethod
    def _time(cls, v: str) -> str:
        v = v.strip()
        if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v


class DischargeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------- helpers ----------

def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def stay_days(admitted_at: str | None, discharge_date: str | None) -> int | None:
    """Bed-days as 2.9 counted them: both the admission and the discharge day count."""
    a, d = to_date(admitted_at), to_date(discharge_date)
    if not a or not d:
        return None
    return (date.fromisoformat(d) - date.fromisoformat(a)).days + 1


def _report_groups() -> list[str]:
    from .report import GROUPS      # report counts bed-days with stay_days from here
    return GROUPS


def _case(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    c = conn.execute(
        "SELECT c.*, p.surname, p.name, p.patronymic, p.dob, p.city, p.street, p.house"
        " FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.id = ? AND c.deleted_at IS NULL",
        (case_id,),
    ).fetchone()
    if c is None:
        raise DischargeError(404, "История не найдена")
    return c


def _record(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM records WHERE case_id = ? AND kind = 'discharge_summary' AND deleted_at IS NULL"
        " ORDER BY recorded_at DESC LIMIT 1", (case_id,)).fetchone()


def _exam(conn: sqlite3.Connection, case_id: str) -> tuple[dict | None, str]:
    """The primary exam's data (if it was saved by fields) and its plain text (for 2.9 HTML-only exams)."""
    row = conn.execute(
        "SELECT data_json, html_legacy FROM records WHERE case_id = ? AND kind = 'primary_exam' AND deleted_at IS NULL"
        " ORDER BY recorded_at LIMIT 1", (case_id,)).fetchone()
    if row is None:
        return None, ""
    data = json.loads(row["data_json"]) if row["data_json"] else None
    return (data if isinstance(data, dict) else None), html_plain(row["html_legacy"] or "")


def _diaries(conn: sqlite3.Connection, case_id: str) -> list[tuple[str, dict]]:
    rows = conn.execute(
        "SELECT recorded_at, data_json FROM records WHERE case_id = ? AND kind = 'diary' AND deleted_at IS NULL"
        " AND data_json IS NOT NULL ORDER BY recorded_at DESC", (case_id,)).fetchall()
    return [(r["recorded_at"], json.loads(r["data_json"])) for r in rows]


def html_plain(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).replace("\xa0", " ")


def after_label(plain: str, label: str) -> str:
    """The rest of the line after «label:» in 2.9's saved text — how 2.9 itself read these fields back."""
    m = re.search(re.escape(label) + r"[ \t]*:[ \t]*(.*)", plain)   # never past the end of the line
    return m[1].strip() if m else ""


_NAME = re.compile(r"^([А-яA-Za-zёЁ][А-яA-Za-zёЁ-]*)")


def treatment_summary(exam: dict | None, diaries: list[tuple[str, dict]], drugs: list[str] = ()) -> str:
    """Drug names from the exam's and the diaries' treatment basis, first word only, no repeats (as 2.9),
    then the drugs on the prescription sheet (2.9 had no working sheet to take them from)."""
    seen: set[str] = set()
    names: list[str] = []

    def take(basis: dict | None) -> None:
        for key in clinical.TREATMENT_LABELS:
            for v in ((basis or {}).get(key) or {}).get("selected") or []:
                v = _s(v)
                m = _NAME.match(v)
                name = m[1] if m else (v.split()[0] if v else "")
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)

    take((exam or {}).get("treatment"))
    for _, d in reversed(diaries):          # oldest first, so the list follows the stay
        take(d.get("basis"))
    for name in drugs:
        if name.strip() and name.strip() not in seen:
            seen.add(name.strip())
            names.append(name.strip())
    return ", ".join(names)


def _vision_of(data: dict) -> dict:
    return {k: _s(data.get(k)) or ("пусто" if k.startswith("vis_correction") else "") for k in VISION_KEYS}


def _has_vision(data: dict) -> bool:
    return any(_s(data.get(k)) for k in ("vis_od", "vis_os", "vgd_od", "vgd_os"))


def local_lines(local: dict) -> list[str]:
    """«OD: Роговица - прозрачная, ...» lines, as 2.9 inserted them into the epicrisis."""
    out = []
    for eye in ("od", "os"):
        parts = []
        for name, cell in (local or {}).items():
            text = exam_mod._cell_text(cell or {}, eye, name)
            if text:
                parts.append(f"{name} - {text}")
        if parts:
            out.append(f"{eye.upper()}: " + ", ".join(parts))
    return out


def _blank() -> dict:
    """Every form key with its default value."""
    return {name: f.get_default(call_default_factory=True) if name != "discharge_date" else ""
            for name, f in DischargeIn.model_fields.items()}


def _from_legacy(rec: sqlite3.Row | None, discharge_json: str | None = None) -> dict:
    """A 2.9 discharge: its payload, with the fields 2.9 kept only in the summary HTML read back from it."""
    data = json.loads(rec["data_json"]) if rec is not None and rec["data_json"] else {}
    if not isinstance(data, dict):
        data = {}
    if rec is not None and rec["html_legacy"]:
        plain = html_plain(rec["html_legacy"])
        data.setdefault("destination", after_label(plain, "Куда направляется выписка"))
        data.setdefault("workplace", after_label(plain, "Место работы и род занятий"))
    if not data.get("epicrisis") and discharge_json:
        data["epicrisis"] = (json.loads(discharge_json) or {}).get("epicrisis", "")
    return data


def saved(conn: sqlite3.Connection, case_id: str) -> dict | None:
    """The saved discharge as form data, or None when the case was never discharged."""
    c = _case(conn, case_id)
    rec = _record(conn, case_id)
    if rec is None and not c["discharged_at"]:
        return None
    data = _from_legacy(rec, c["discharge_json"])
    out = _blank()
    out.update({k: v for k, v in data.items() if k in out})
    out["discharge_date"] = to_date(data.get("discharge_date")) or to_date(c["discharged_at"]) or date.today().isoformat()
    out["discharge_time"] = _s(data.get("discharge_time")) or (c["discharged_at"] or "")[11:16]
    out["outcome"] = c["outcome"] or _s(data.get("outcome"))
    out["final_diagnosis"] = c["dx_final"] or _s(data.get("final_diagnosis"))
    out["recommendations"] = c["recommendations"] or _s(data.get("recommendations"))
    return out


# ---------- the form ----------

def draft(conn: sqlite3.Connection, case_id: str) -> dict:
    c = _case(conn, case_id)
    exam, exam_plain = _exam(conn, case_id)
    diaries = _diaries(conn, case_id)
    existing = saved(conn, case_id)

    admission_vision = _vision_of(exam) if exam and _has_vision(exam) else None
    last_vis = next(((at, d) for at, d in diaries if _has_vision(d)), None)
    local_at_admission = exam_mod.complete(exam)["local"] if exam and exam.get("local") else {}
    last_text = next(((at, d) for at, d in diaries
                      if any(_s(d.get(f"{e}_text")) for e in ("od", "os", "ou"))), None)
    complaints = _s((exam or {}).get("complaints")) or after_label(exam_plain, "Жалобы")
    # Recommendations written in the last diary before discharge («Для выписки» → «Рекомендации»).
    diary_rec = next(((at, _s(d.get("recommendations"))) for at, d in diaries if _s(d.get("recommendations"))), None)
    comorbid = c["dx_comorbid"] or (exam_mod.comorbid_text(exam) if exam else "")

    if existing:
        form = existing
    else:
        now = datetime.now()
        form = _blank()
        form.update({
            "discharge_date": now.date().isoformat(), "discharge_time": now.strftime("%H:%M"),
            "outcome": OUTCOMES[0],
            "final_diagnosis": c["dx_clinical"] or c["dx_admission"],
            "treatment_summary": treatment_summary(exam, diaries, [r["name"] for r in conn.execute(
                "SELECT name FROM prescriptions WHERE case_id = ? AND category = 'drugs' AND deleted_at IS NULL"
                " ORDER BY COALESCE(date_from, ''), created_at", (case_id,))]),
            "discharge_local": local_at_admission,
            "recommendations": diary_rec[1] if diary_rec else "",       # «Лечебные и трудовые рекомендации»
            **(_vision_of(last_vis[1]) if last_vis else {}),
        })
        # The workplace rarely changes between stays: take it from the patient's last discharge.
        prev = conn.execute(
            "SELECT r.data_json, r.html_legacy FROM records r JOIN cases c ON c.id = r.case_id"
            " WHERE c.patient_id = ? AND c.id != ? AND r.kind = 'discharge_summary' AND r.deleted_at IS NULL"
            " ORDER BY r.recorded_at DESC LIMIT 1", (c["patient_id"], case_id)).fetchone()
        if prev is not None:
            form["workplace"] = _s(_from_legacy(prev).get("workplace"))

    from .report import GROUPS, suggest_group
    form["report_group"] = (form.get("report_group") or c["report_group"]
                            or suggest_group(form["final_diagnosis"] or c["dx_clinical"] or c["dx_admission"]))

    study_rows = [studies_mod.view(s) for s in conn.execute(
        "SELECT * FROM studies WHERE case_id = ? AND deleted_at IS NULL ORDER BY study_date", (case_id,))]

    return {
        "case": {
            "id": c["id"], "number": c["number"], "medCard": c["med_card"], "status": c["status"],
            "admittedAt": c["admitted_at"], "dischargedAt": c["discharged_at"],
            "patient": " ".join(x for x in (c["surname"], c["name"], c["patronymic"]) if x),
            "dob": c["dob"], "address": ", ".join(x for x in (c["city"], c["street"], c["house"]) if x),
            "dxAdmission": c["dx_admission"], "dxClinical": c["dx_clinical"], "dxComorbid": comorbid,
        },
        "saved": existing is not None,
        "form": form,
        "sources": {
            "admissionVision": admission_vision,
            "dischargeVisionFrom": last_vis[0][:10] if last_vis and not existing else None,
            "localFrom": "первичный осмотр" if local_at_admission and not existing else None,
            "complaints": complaints,
            "lastDiary": {"date": last_text[0][:10], **{e: _s(last_text[1].get(f"{e}_text")) for e in ("od", "os", "ou")}}
                         if last_text else None,
            # «10.04.2026 ОАК: Hb 128; ...» — the line 2.9 inserted into the epicrisis
            "studies": [{"id": s["id"], "line": " ".join(x for x in [
                _date_ru(s["date"]) if s["date"] else (s["unparsedDate"] or ""), s["name"]] if x)
                + (f": {s['result'].replace(chr(10), '; ')}" if s["result"] else "")} for s in study_rows],
            "recentRecommendations": _recent(conn, "recommendations"),
            "diaryRecommendations": {"date": diary_rec[0][:10], "text": diary_rec[1]} if diary_rec else None,
            "recentDestinations": _recent_destinations(conn),
        },
        "options": {
            "outcomes": OUTCOMES,
            "reportGroups": GROUPS,
            "local": exam_mod.LOCAL_OPTIONS,
            "anterior": exam_mod.ANTERIOR_OPTIONS,
            "anteriorRow": exam_mod.ANTERIOR,
        },
    }


def _date_ru(iso: str | None) -> str:
    d = to_date(iso)
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if d else ""


def _recent(conn: sqlite3.Connection, column: str, limit: int = 6) -> list[dict]:
    """Recent distinct texts with the diagnosis they were written for — to start from instead of typing."""
    out, seen = [], set()
    for r in conn.execute(f"SELECT {column} AS text, dx_final FROM cases WHERE {column} != '' AND deleted_at IS NULL"
                          " ORDER BY COALESCE(discharged_at, updated_at) DESC LIMIT 200"):
        key = r["text"].strip()
        if key and key not in seen:
            seen.add(key)
            out.append({"text": key, "dx": r["dx_final"]})
        if len(out) >= limit:
            break
    return out


def _recent_destinations(conn: sqlite3.Connection, limit: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for r in conn.execute("SELECT data_json, html_legacy FROM records WHERE kind = 'discharge_summary'"
                          " AND deleted_at IS NULL ORDER BY recorded_at DESC LIMIT 300"):
        data = json.loads(r["data_json"]) if r["data_json"] else {}
        dest = _s((data or {}).get("destination")) or after_label(html_plain(r["html_legacy"] or ""), "Куда направляется выписка")
        if dest:
            counts[dest] = counts.get(dest, 0) + 1
    return [d for d, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:limit]


def save(conn: sqlite3.Connection, case_id: str, d: DischargeIn) -> str:
    c = _case(conn, case_id)
    if c["status"] == "archived":
        raise DischargeError(409, "История в архиве — сначала верните её из архива")
    days = stay_days(c["admitted_at"], d.discharge_date)
    if days is not None and days <= 0:
        raise DischargeError(422, "Дата выписки не может быть раньше даты поступления")

    payload = d.model_dump()
    payload["local_status_text"] = "\n".join(local_lines(d.discharge_local))
    data = json.dumps(payload, ensure_ascii=False)
    discharged_at = f"{d.discharge_date}T{d.discharge_time}" if d.discharge_time else d.discharge_date
    ts = store.now_iso()
    rec = _record(conn, case_id)
    with conn:
        if rec is None:
            rid = store.new_id()
            conn.execute(
                "INSERT INTO records (id, case_id, kind, recorded_at, data_json, created_at, updated_at)"
                " VALUES (?, ?, 'discharge_summary', ?, ?, ?, ?)",
                (rid, case_id, f"{d.discharge_date}T{d.discharge_time or '00:00'}", data, ts, ts))
        else:
            rid = rec["id"]
            conn.execute("UPDATE records SET data_json = ?, recorded_at = ?, updated_at = ? WHERE id = ?",
                         (data, f"{d.discharge_date}T{d.discharge_time or '00:00'}", ts, rid))
        conn.execute(
            "UPDATE cases SET status = 'discharged', discharged_at = ?, outcome = ?, dx_final = ?,"
            " recommendations = ?, discharge_json = ?, report_group = ?, updated_at = ? WHERE id = ?",
            (discharged_at, d.outcome.strip(), d.final_diagnosis.strip(), d.recommendations.strip(),
             data, d.report_group.strip() if d.report_group.strip() in _report_groups() else "", ts, case_id))
    return rid


# ---------- status changes ----------

def archive(conn: sqlite3.Connection, case_id: str) -> None:
    c = _case(conn, case_id)
    if c["status"] == "archived":
        return
    if c["status"] != "discharged":
        raise DischargeError(409, "Сначала оформите выписку, потом переносите историю в архив")
    ts = store.now_iso()
    with conn:
        conn.execute("UPDATE cases SET status = 'archived', archived_at = ?, updated_at = ? WHERE id = ?",
                     (ts, ts, case_id))


def unarchive(conn: sqlite3.Connection, case_id: str) -> None:
    """Back from the archive to the department list, still discharged (to fix or reprint something)."""
    c = _case(conn, case_id)
    if c["status"] != "archived":
        raise DischargeError(409, "История не в архиве")
    with conn:
        conn.execute("UPDATE cases SET status = 'discharged', archived_at = NULL, updated_at = ? WHERE id = ?",
                     (store.now_iso(), case_id))


def reopen(conn: sqlite3.Connection, case_id: str) -> None:
    """Undo the discharge: the patient is in the department again. The filled-in form is kept."""
    c = _case(conn, case_id)
    if c["status"] == "archived":
        raise DischargeError(409, "История в архиве — сначала верните её из архива")
    if c["status"] == "active":
        return
    if conn.execute("SELECT 1 FROM cases WHERE patient_id = ? AND id != ? AND status = 'active' AND deleted_at IS NULL",
                    (c["patient_id"], case_id)).fetchone():
        raise DischargeError(409, "У пациента уже есть другая открытая история")
    with conn:
        conn.execute("UPDATE cases SET status = 'active', discharged_at = NULL, updated_at = ? WHERE id = ?",
                     (store.now_iso(), case_id))
