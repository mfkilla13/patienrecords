"""The printed лист назначений (2.9 had only a stub): an A4 document in the look of the выписка.

The patient, then the prescriptions by section (стол и режим, обследования, препараты, ЛФК)
with their dates; cancelled ones stay on the sheet with the date of cancellation, as on the
paper form. Not part of the case sheets, so it is printed as often as needed.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import date

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Spacer, Table, TableStyle

from . import prescriptions as rx
from . import printjobs, settings
from .dischargeprint import BOTTOM_MM, HEAD, SUB, TEXT, TITLE, TOP_MM, Signatures, _box, _label_cell, _page, full_date
from .printlayout import CONTENT_W, FONT_SEMI, GREY, MARGIN_X, PAGE_H, PAGE_W, _date_ru, _esc, _p

SMALL = ParagraphStyle("rxsmall", parent=TEXT, fontSize=8.5, leading=11)


def _case(conn: sqlite3.Connection, case_id: str) -> dict:
    c = conn.execute(
        "SELECT c.*, p.surname, p.name, p.patronymic, p.dob FROM cases c JOIN patients p ON p.id = c.patient_id"
        " WHERE c.id = ? AND c.deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise rx.PrescriptionError(404, "История не найдена")
    return {"number": c["number"], "patient": " ".join(x for x in (c["surname"], c["name"], c["patronymic"]) if x),
            "dob": c["dob"], "admittedAt": c["admitted_at"],
            "dx": c["dx_final"] or c["dx_clinical"] or c["dx_admission"] or "", "comorbid": c["dx_comorbid"] or ""}


def _d(iso: str | None) -> str:
    return _date_ru(iso) if iso else ""


def _section(title: str, items: list[dict], plain: bool) -> list:
    head = ["№", "Назначение"] + ([] if plain else ["Способ", "Кратность"]) + ["Назначено", "Отменено"]
    rows = [[_p(f"<font name='{FONT_SEMI}' color='{GREY}'>{h}</font>", SMALL) for h in head]]
    for i, it in enumerate(items, 1):
        cells = [str(i), _esc(it["name"])] + ([] if plain else [_esc(it["method"]), _esc(it["freq"])])
        cells += [_d(it["dateFrom"]), _d(it["dateTo"])]
        rows.append([_p(x or "&nbsp;", TEXT) for x in cells])
    num, dates = 8 * mm, 22 * mm
    if plain:
        widths = [num, CONTENT_W - num - 2 * dates, dates, dates]
    else:
        widths = [num, CONTENT_W - num - 2 * dates - 24 * mm - 30 * mm, 24 * mm, 30 * mm, dates, dates]
    t = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.9, "black"), ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        *[("LINEBELOW", (0, r), (-1, r), 0.4, "#c8c8c8") for r in range(len(rows) - 1)],
    ]))
    part = [_p(title, HEAD), Spacer(0, 1), t]
    # A short section stays with its heading; a long one may break (the header row repeats).
    return [KeepTogether(part) if len(rows) <= 8 else part[0], *([] if len(rows) <= 8 else part[1:]), Spacer(0, 3 * mm)]


def story(case: dict, items: list[dict], s: dict) -> list:
    out: list = [Spacer(0, 13 * mm), _p("ЛИСТ НАЗНАЧЕНИЙ", TITLE), _p("медицинской карты стационарного больного", SUB),
                 Spacer(0, 5 * mm)]
    first = 46 * mm
    rows = [("Фамилия, имя, отчество", f"<b>{_esc(case['patient'])}</b>"),
            ("Дата рождения", _d(case["dob"])),
            ("История болезни", f"№ {_esc(case['number'])}, поступление {_d(case['admittedAt'])}"),
            ("Диагноз", _esc(case["dx"]))]
    if case["comorbid"]:
        rows.append(("Сопутствующий", _esc(case["comorbid"])))
    out += [_box([[_label_cell(a), _p(b or "&nbsp;", TEXT)] for a, b in rows], [first, CONTENT_W - first]), Spacer(0, 4 * mm)]

    for key, title in rx.CATEGORIES.items():
        part = [it for it in items if it["category"] == key]
        if part:
            out += _section(title, part, key in rx.PLAIN)
    other = [it for it in items if it["category"] not in rx.CATEGORIES]
    if other:                       # carried over from 2.9 without a section
        out += _section("Назначения", other, False)
    if not items:
        out.append(_p("Назначений нет.", TEXT))

    doctor = (s["doctor_signature"] or "").strip()
    out += [Spacer(0, 6 * mm), KeepTogether([Signatures(full_date(date.today().isoformat()),
                                                        [f"Лечащий врач {doctor}".strip()])])]
    return out


def pdf(conn: sqlite3.Connection, case_id: str) -> bytes:
    case = _case(conn, case_id)
    items = rx.listing(conn, case_id)["items"]
    s = settings.get(conn)
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                          topMargin=TOP_MM * mm, bottomMargin=BOTTOM_MM * mm,
                          title=f"Лист назначений — {case['patient']}", author="MedQT")
    frame = Frame(MARGIN_X, BOTTOM_MM * mm, CONTENT_W, PAGE_H - (TOP_MM + BOTTOM_MM) * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=_page(case, s, "лист назначений"))])
    doc.build(story(case, items, s))
    return buf.getvalue()


@printjobs._serialized
def preview_png(conn: sqlite3.Connection, case_id: str, page: int, dpi: int = 110) -> tuple[bytes, int]:
    import pypdfium2

    doc = pypdfium2.PdfDocument(pdf(conn, case_id))
    if not 1 <= page <= len(doc):
        raise rx.PrescriptionError(404, "Нет такой страницы")
    out = io.BytesIO()
    doc[page - 1].render(scale=dpi / 72).to_pil().convert("RGB").save(out, "PNG")
    return out.getvalue(), len(doc)


@printjobs._serialized
def pages(conn: sqlite3.Connection, case_id: str) -> int:
    import pypdfium2

    return len(pypdfium2.PdfDocument(pdf(conn, case_id)))


def send(conn: sqlite3.Connection, case_id: str, printer: str, copies: int = 1) -> None:
    from . import winprint

    data = pdf(conn, case_id)
    for _ in range(max(1, min(copies, 5))):
        winprint.print_pdf(data, printer, f"MedQT — лист назначений ({date.today():%d.%m.%Y})")
