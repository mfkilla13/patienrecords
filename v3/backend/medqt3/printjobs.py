"""Print jobs: plan, lay out, print, then confirm.

Every record printed by v3 has a fixed place on the case's sheets (sheet + mm),
like in 2.9 — but stored, not re-derived by re-rendering the whole history in
white, so nothing drifts and back-dated edits cannot shift other records.

Two kinds of job:
  sheet — the real record sheet: unprinted records continue below the last print
          (or on a new sheet / from a given offset), and already printed records
          that are ticked are reprinted exactly in their own place.
  copy  — the ticked records one after another on a clean sheet or from an offset;
          an extra copy, nothing is marked.

Only after the doctor confirms the sheet came out right are new records marked
printed and their places stored. A cancelled job changes nothing.
"""

from __future__ import annotations

import functools
import io
import json
import sqlite3
import threading
from datetime import date

from . import clinical, printlayout, settings
from . import db as store

PRINTABLE = ("primary_exam", "diary", "operation_protocol", "other")
KIND_ORDER = {"primary_exam": 0, "diary": 1, "operation_protocol": 2, "other": 3}
MIN_SPACE_MM = 25.0   # if less than this is left on the sheet, suggest a new one

# pdfium is not thread-safe and the browser asks for several page images at once
# (each handled in its own worker thread), so all PDF work runs one at a time.
_lock = threading.RLock()
_pdf_cache: dict[str, bytes] = {}


def forget_cache() -> None:
    with _lock:
        _pdf_cache.clear()


def _serialized(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper


class PrintError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _doctor(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'doctor_signature'").fetchone()
    return row["value"] if row and row["value"] else ""


def _printable_reason(row: sqlite3.Row) -> str | None:
    if row["kind"] not in PRINTABLE:
        return "не печатается в листе дневников"
    if row["kind"] == "primary_exam" and row["html_legacy"]:
        return None   # printed from its saved 2.9 text, like 2.9 did
    if not row["data_json"]:
        return "запись из 2.9 без полей и без сохранённого текста"
    return None


def _state(conn: sqlite3.Connection, case_id: str) -> dict | None:
    s = conn.execute("SELECT sheet, used_mm, last_printed_at, source FROM print_state WHERE case_id = ?",
                     (case_id,)).fetchone()
    return dict(s) if s else None


def _positions(conn: sqlite3.Connection, case_id: str) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT pp.* FROM print_positions pp JOIN records r ON r.id = pp.record_id WHERE r.case_id = ?",
        (case_id,)).fetchall()
    return {r["record_id"]: dict(r) for r in rows}


def _sort_key(r) -> tuple:
    return (r["recorded_at"][:10], KIND_ORDER.get(r["kind"], 9), r["recorded_at"])


def _case_records(conn: sqlite3.Connection, case_id: str) -> list[sqlite3.Row]:
    case = conn.execute("SELECT id FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if case is None:
        raise PrintError(404, "История не найдена")
    rows = conn.execute(
        "SELECT * FROM records WHERE case_id = ? AND deleted_at IS NULL AND (kind IN"
        " ('primary_exam', 'diary', 'operation_protocol') OR (kind = 'other' AND data_json IS NOT NULL))",
        (case_id,)).fetchall()
    return sorted(rows, key=_sort_key)


def _day(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}"


@_serialized
def plan(conn: sqlite3.Connection, case_id: str) -> dict:
    rows = _case_records(conn, case_id)
    positions = _positions(conn, case_id)
    records = []
    for r in rows:
        view = clinical.record_view(r)
        reason = _printable_reason(r)
        by_label = {s["label"]: s["text"] for s in view["sections"]}
        summary = next((by_label[k] for k in ("OD", "OS", "OU", "Операция", "Жалобы", "") if by_label.get(k)), "")
        pos = positions.get(r["id"])
        records.append({
            "id": r["id"], "kind": r["kind"], "kindLabel": view["kindLabel"], "recordedAt": view["recordedAt"],
            "printedAt": r["printed_at"], "printable": reason is None, "reason": reason, "summary": summary[:120],
            "place": {"sheet": pos["start_sheet"], "startMm": pos["start_mm"]} if pos else None,
        })
    state = _state(conn, case_id)
    v3 = state if state and state["source"] == "v3" else None
    if v3 and v3["used_mm"] + printlayout.GAP_MM < printlayout.LAST_LINE_MM - MIN_SPACE_MM:
        suggestion = {"mode": "continue", "sheet": v3["sheet"], "startMm": round(v3["used_mm"] + printlayout.GAP_MM, 1)}
    else:
        suggestion = {"mode": "new", "sheet": v3["sheet"] + 1 if v3 else 1, "startMm": printlayout.MARGIN_TOP_MM}
    last_on_sheet = None
    if v3:
        on_sheet = [r for r in rows if r["id"] in positions and positions[r["id"]]["end_sheet"] == v3["sheet"]]
        if on_sheet:
            last_on_sheet = _day(on_sheet[-1]["recorded_at"])
    return {"state": state, "records": records, "suggestion": suggestion, "doctor": _doctor(conn),
            "lastOnSheet": last_on_sheet}


def _block(r: sqlite3.Row, doctor: str) -> list:
    if r["kind"] == "primary_exam" and r["html_legacy"] and (r["legacy_id"] is not None or not r["data_json"]):
        # Exams written in 2.9 print from the text the doctor saw and signed then.
        return printlayout.legacy_exam_block(r["html_legacy"], r["recorded_at"], doctor)
    data = json.loads(r["data_json"])
    if r["kind"] == "diary":
        return printlayout.diary_block(data, r["recorded_at"], doctor)
    if r["kind"] == "operation_protocol":
        return printlayout.protocol_block(data, r["recorded_at"], doctor)
    if r["kind"] == "other":
        return printlayout.text_block(data, r["recorded_at"], doctor)
    return printlayout.exam_block(data, r["recorded_at"], doctor)


def _sheet_info(conn: sqlite3.Connection, case_id: str) -> printlayout.SheetInfo:
    """What the heading of a fresh sheet shows: department, institution and the patient."""
    c = conn.execute("SELECT c.number, c.med_card, c.admitted_at, p.surname, p.name, p.patronymic, p.dob FROM cases c"
                     " JOIN patients p ON p.id = c.patient_id WHERE c.id = ?", (case_id,)).fetchone()
    s = settings.get(conn)
    lines = [ln.strip() for ln in s["org_header"].splitlines() if ln.strip()]
    org = " · ".join([" ".join(lines[:-1]), lines[-1]] if len(lines) > 1 else lines)
    initials = "".join(f"{x[0]}. " for x in (c["name"], c["patronymic"]) if x).strip()
    return printlayout.SheetInfo(
        department=s["department"] or "Офтальмологическое отделение", org_line=org,
        patient=" ".join(x for x in (c["surname"], c["name"], c["patronymic"]) if x),
        dob=printlayout._date_ru(c["dob"]) if c["dob"] else "", number=printlayout.paper_number(c["med_card"]),
        admitted=printlayout._date_ru(c["admitted_at"]) if c["admitted_at"] else "",
        short=f"{c['surname']} {initials} · история № {printlayout.paper_number(c['med_card'])}".replace("  ", " "))


def _selected(conn: sqlite3.Connection, case_id: str, record_ids: list[str]) -> list[sqlite3.Row]:
    if not record_ids:
        raise PrintError(422, "Не выбрано ни одной записи")
    by_id = {r["id"]: r for r in _case_records(conn, case_id)}
    if any(i not in by_id for i in record_ids):
        raise PrintError(404, "Часть записей не найдена")
    rows = sorted((by_id[i] for i in set(record_ids)), key=_sort_key)
    for r in rows:
        reason = _printable_reason(r)
        if reason:
            raise PrintError(422, f"Запись от {_day(r['recorded_at'])}: {reason}")
    return rows


def _flow(blocks: list[list], sheet: int, start_mm: float) -> tuple[list[dict], bool]:
    """Places for records printed one after another from (sheet, start_mm); moves to a new sheet when
    the first record does not fit on what is left, so a blank page is never sent to the printer."""
    layout = printlayout.build(blocks, start_mm)
    moved = layout.start_page > 1
    if moved:
        sheet, layout = sheet + 1, printlayout.build(blocks, printlayout.MARGIN_TOP_MM)
    places = [{"startSheet": sheet + p.start_page - 1, "startMm": p.start_mm,
               "endSheet": sheet + p.end_page - 1, "endMm": p.end_mm} for p in layout.places]
    return places, moved


def _shade(pos: dict, sheet: int) -> list[float] | None:
    """The part of `sheet` a stored record occupies, as [top_mm, bottom_mm]."""
    if not pos["start_sheet"] <= sheet <= pos["end_sheet"]:
        return None
    top = pos["start_mm"] if pos["start_sheet"] == sheet else printlayout.MARGIN_TOP_MM
    bottom = pos["end_mm"] if pos["end_sheet"] == sheet else printlayout.LAST_LINE_MM
    return [round(top, 1), round(bottom, 1)]


@_serialized
def create_job(conn: sqlite3.Connection, case_id: str, record_ids: list[str], mode: str,
               start_mm: float | None = None, kind: str = "sheet", handwritten_to: float | None = None,
               handwritten_sheet: int | None = None) -> dict:
    """mode (where unprinted records go): continue | new | manual (start_mm on the current sheet).

    handwritten_to / handwritten_sheet: when continuing, another doctor may have written by hand below our
    last print, possibly running over onto the next sheet(s); printing then starts below where the
    handwriting ends — on that sheet — instead of on top of it."""
    rows = _selected(conn, case_id, record_ids)
    positions = _positions(conn, case_id)
    state = _state(conn, case_id)
    v3 = state if state and state["source"] == "v3" else None
    current_sheet = v3["sheet"] if v3 else 1
    doctor = _doctor(conn)

    if kind == "sheet":
        flowing = [r for r in rows if not r["printed_at"]]
        in_place = [r for r in rows if r["printed_at"]]
        no_place = [r for r in in_place if r["id"] not in positions]
        if no_place:
            raise PrintError(422, f"Запись от {_day(no_place[0]['recorded_at'])} напечатана в версии 2.9 — её места "
                                  "на листе программа не знает. Перепечатайте её копией подряд.")
    elif kind == "copy":
        flowing, in_place = rows, []
    else:
        raise PrintError(422, "Неизвестный вид печати")

    placements: list[dict] = []
    moved = False
    new_start = None
    if flowing:
        if mode == "continue":
            if kind == "copy" or not v3:
                raise PrintError(409, "Продолжить можно только лист, напечатанный в новой версии — "
                                      "выберите новый лист или отступ")
            sheet, start = current_sheet, v3["used_mm"] + printlayout.GAP_MM
            if handwritten_to is not None:
                hw_sheet = handwritten_sheet or current_sheet
                if not current_sheet <= hw_sheet <= current_sheet + 2:
                    raise PrintError(422, f"Рукописная запись может кончаться на листе {current_sheet}–{current_sheet + 2}")
                low = v3["used_mm"] if hw_sheet == current_sheet else 5.0
                if not (low <= handwritten_to <= printlayout.LAST_LINE_MM):
                    raise PrintError(422, f"Рукописная запись на листе {hw_sheet} должна заканчиваться между "
                                          f"{low:.0f} и {printlayout.LAST_LINE_MM:.0f} мм")
                if hw_sheet > current_sheet:   # it ran over: continue on the sheet where it ends
                    sheet, start = hw_sheet, handwritten_to + printlayout.GAP_MM
                else:
                    start = max(start, handwritten_to + printlayout.GAP_MM)
        elif mode == "new":
            sheet, start = (current_sheet + 1 if v3 and kind == "sheet" else 1), printlayout.MARGIN_TOP_MM
        elif mode == "manual":
            if start_mm is None or not (5 <= start_mm <= printlayout.LAST_LINE_MM - 10):
                raise PrintError(422, f"Отступ должен быть от 5 до {printlayout.LAST_LINE_MM - 10:.0f} мм")
            sheet, start = (current_sheet if kind == "sheet" else 1), float(start_mm)
        else:
            raise PrintError(422, "Неизвестный режим печати")
        places, moved = _flow([_block(r, doctor) for r in flowing], sheet, start)
        for r, p in zip(flowing, places):
            placements.append({"recordId": r["id"], "isNew": kind == "sheet", **p})
        new_start = {"sheet": places[0]["startSheet"], "mm": round(places[0]["startMm"], 1)}
    for r in in_place:
        p = positions[r["id"]]
        placements.append({"recordId": r["id"], "isNew": False, "startSheet": p["start_sheet"],
                           "startMm": p["start_mm"], "endSheet": p["end_sheet"], "endMm": p["end_mm"]})
    placements.sort(key=lambda p: (p["startSheet"], p["startMm"]))

    # Sheets with handwriting are not empty, whatever our records say: no heading over the handwriting.
    hw_sheets = (set(range(current_sheet, (handwritten_sheet or current_sheet) + 1))
                 if mode == "continue" and handwritten_to is not None else set())
    fresh = _fresh_sheets(placements, positions, kind) - hw_sheets
    pdf, sheets = _render(conn, case_id, placements, doctor, fresh)
    selected = {p["recordId"] for p in placements}
    pages = []
    for s in sheets:
        shade = [] if kind == "copy" else [x for rid, pos in positions.items() if rid not in selected
                                           for x in [_shade(pos, s)] if x]
        hw_end_sheet = handwritten_sheet or current_sheet
        if mode == "continue" and handwritten_to is not None and s == hw_end_sheet and not moved:
            top = v3["used_mm"] if s == current_sheet else printlayout.SHEET_TOP_MM
            shade.append([round(top, 1), round(handwritten_to, 1)])   # the handwriting, shown as already on paper
        known_on_sheet = any(_shade(pos, s) for pos in positions.values())
        if (mode == "manual" and new_start and s == new_start["sheet"]
                and new_start["mm"] > printlayout.MARGIN_TOP_MM + 0.5 and not known_on_sheet):
            # A manual offset on a sheet we know nothing about (e.g. printed by 2.9): shade the band above it.
            shade = [[printlayout.SHEET_TOP_MM, new_start["mm"] - 1.5]]
        has_old = bool(shade) or any(p["startSheet"] <= s <= p["endSheet"] and not p["isNew"] and kind == "sheet"
                                     for p in placements)
        if s in fresh:
            insert = "чистый лист" if kind == "copy" else f"чистый лист — это будет лист {s}"
        elif s in hw_sheets and s == hw_end_sheet and s != current_sheet:
            insert = f"лист {s} (на нём запись от руки до {handwritten_to:.0f} мм)"
        elif kind == "copy":
            insert = "лист, на котором верх уже занят"
        elif has_old:
            last = max((rid for rid, pos in positions.items() if _shade(pos, s)),
                       key=lambda rid: positions[rid]["end_mm"], default=None)
            last_row = next((r for r in _case_records(conn, case_id) if r["id"] == last), None)
            insert = f"лист {s}" + (f" (на нём записи до {_day(last_row['recorded_at'])})" if last_row else " с прошлой печатью")
        else:
            insert = f"чистый лист — это будет лист {s}"
        pages.append({"sheet": s, "insert": insert, "shade": shade, "fresh": s in fresh})

    new_places = [p for p in placements if p["isNew"]]
    new_end = max(new_places, key=lambda p: (p["endSheet"], p["endMm"])) if new_places else None
    job_id, ts = store.new_id(), store.now_iso()
    with conn:
        conn.execute(
            "INSERT INTO print_jobs (id, case_id, kind, record_ids, placements, pages, new_end_sheet, new_end_mm,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, case_id, kind, json.dumps(sorted(selected)), json.dumps(placements), json.dumps(pages),
             new_end["endSheet"] if new_end else None, new_end["endMm"] if new_end else None, ts, ts))
    _pdf_cache[job_id] = pdf
    last = placements[-1]
    return {
        "jobId": job_id, "kind": kind, "pages": pages, "movedToNewSheet": moved, "newStart": new_start,
        "newEnd": {"sheet": new_end["endSheet"], "mm": new_end["endMm"]} if new_end else None,
        "leftMm": round(printlayout.LAST_LINE_MM - last["endMm"], 1),
        "newCount": len(new_places), "reprintCount": len(in_place), "count": len(placements),
    }


def _fresh_sheets(placements: list[dict], positions: dict[str, dict], kind: str) -> set[int]:
    """Sheets that start empty in this print: they get the heading and «лист N». A sheet already holding
    a stored record, or one where printing starts lower down (continuing it), is not fresh."""
    fresh = set()
    for s in {x for p in placements for x in range(p["startSheet"], p["endSheet"] + 1)}:
        if kind == "sheet" and any(_shade(pos, s) for pos in positions.values()):
            continue
        starts = [p["startMm"] for p in placements if p["startSheet"] == s]
        # On a following sheet the first record starts one gap lower (the gap between records).
        if not starts or min(starts) <= printlayout.CONTENT_TOP_MM + printlayout.GAP_MM + 0.5:
            fresh.add(s)
    return fresh


def _render(conn: sqlite3.Connection, case_id: str, placements: list[dict], doctor: str,
            fresh: set[int]) -> tuple[bytes, list[int]]:
    by_id = {r["id"]: r for r in _case_records(conn, case_id)}
    items = [(_block(by_id[p["recordId"]], doctor), p["startSheet"], p["startMm"]) for p in placements]
    return printlayout.render_fixed(items, _sheet_info(conn, case_id), fresh)


def _job(conn: sqlite3.Connection, job_id: str) -> sqlite3.Row:
    job = conn.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        raise PrintError(404, "Задание печати не найдено")
    return job


@_serialized
def pdf(conn: sqlite3.Connection, job_id: str) -> bytes:
    job = _job(conn, job_id)
    if job_id not in _pdf_cache:  # e.g. after a restart: rebuild exactly the same placements
        fresh = {p["sheet"] for p in json.loads(job["pages"]) if p.get("fresh")}
        _pdf_cache[job_id] = _render(conn, job["case_id"], json.loads(job["placements"]), _doctor(conn), fresh)[0]
    return _pdf_cache[job_id]


@_serialized
def preview_png(conn: sqlite3.Connection, job_id: str, page: int, dpi: int = 110) -> bytes:
    """Page image; the parts of the sheet already printed earlier are shaded, the new start is dashed."""
    import pypdfium2
    from PIL import ImageDraw

    job = _job(conn, job_id)
    doc = pypdfium2.PdfDocument(pdf(conn, job_id))
    if not 1 <= page <= len(doc):
        raise PrintError(404, "Нет такой страницы")
    img = doc[page - 1].render(scale=dpi / 72).to_pil().convert("RGB")
    info = json.loads(job["pages"])[page - 1]
    px = lambda v: int(v / 25.4 * dpi)  # noqa: E731
    draw = ImageDraw.Draw(img, "RGBA")
    for top, bottom in info["shade"]:
        draw.rectangle([px(15), px(top), img.width - px(15), px(bottom)], fill=(217, 211, 201, 255))
    # The dashed "printing starts here" line goes only where the new records begin, not on later sheets.
    news = [p for p in json.loads(job["placements"]) if p["isNew"]]
    first = min(news, key=lambda p: (p["startSheet"], p["startMm"])) if news else None
    if first and first["startSheet"] == info["sheet"] and first["startMm"] > printlayout.MARGIN_TOP_MM + 0.5:
        y = px(first["startMm"] - 1)
        for x in range(0, img.width, 14):
            draw.line([(x, y), (x + 7, y)], fill=(46, 107, 79, 255), width=2)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@_serialized
def confirm(conn: sqlite3.Connection, job_id: str) -> dict:
    job = _job(conn, job_id)
    if job["status"] != "pending":
        raise PrintError(409, "Это задание уже закрыто")
    ts = store.now_iso()
    new = [p for p in json.loads(job["placements"]) if p["isNew"]]
    with conn:
        for p in new:
            conn.execute("UPDATE records SET printed_at = COALESCE(printed_at, ?), print_batch = ?, updated_at = ?"
                         " WHERE id = ?", (ts, job_id, ts, p["recordId"]))
            conn.execute(
                "INSERT OR REPLACE INTO print_positions (record_id, start_sheet, start_mm, end_sheet, end_mm, job_id,"
                " updated_at) VALUES (?,?,?,?,?,?,?)",
                (p["recordId"], p["startSheet"], p["startMm"], p["endSheet"], p["endMm"], job_id, ts))
        if job["new_end_sheet"] is not None:
            conn.execute(
                "INSERT INTO print_state (case_id, sheet, used_mm, last_printed_at, last_batch, source, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'v3', ?) ON CONFLICT(case_id) DO UPDATE SET sheet = excluded.sheet,"
                " used_mm = excluded.used_mm, last_printed_at = excluded.last_printed_at,"
                " last_batch = excluded.last_batch, source = 'v3', updated_at = excluded.updated_at",
                (job["case_id"], job["new_end_sheet"], job["new_end_mm"], ts, job_id, ts))
        conn.execute("UPDATE print_jobs SET status = 'confirmed', updated_at = ? WHERE id = ?", (ts, job_id))
    _pdf_cache.pop(job_id, None)
    return {"marked": len(new), "sheet": job["new_end_sheet"], "usedMm": job["new_end_mm"]}


@_serialized
def cancel(conn: sqlite3.Connection, job_id: str) -> None:
    job = _job(conn, job_id)
    if job["status"] == "pending":
        with conn:
            conn.execute("UPDATE print_jobs SET status = 'cancelled', updated_at = ? WHERE id = ?",
                         (store.now_iso(), job_id))
    _pdf_cache.pop(job_id, None)


@_serialized
def send_to_printer(conn: sqlite3.Connection, job_id: str, printer: str, output_file: str | None = None) -> None:
    from . import winprint

    job = _job(conn, job_id)
    if job["status"] != "pending":
        raise PrintError(409, "Это задание уже закрыто")
    winprint.print_pdf(pdf(conn, job_id), printer, f"MedQT — дневники ({date.today():%d.%m.%Y})", output_file)
    with conn:
        conn.execute("UPDATE print_jobs SET printer = ?, updated_at = ? WHERE id = ?", (printer, store.now_iso(), job_id))
