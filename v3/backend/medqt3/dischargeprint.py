"""The printed выписка: 2.9's form (header, «В», items 1–8, signatures) in the «В стиле программы» look.

A separate A4 document, not part of the case sheets, so it has no stored position:
it is simply printed (as many copies as needed) whenever the doctor asks.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import date

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, KeepTogether, PageTemplate, Spacer, Table, TableStyle

from . import discharge as dis
from . import printjobs, settings
from .clinical import vision as vision_of
from .printlayout import (BODY, CONTENT_W, FONT, FONT_BOLD, FONT_SEMI, GREY, MARGIN_X, PAGE_H, PAGE_W,
                          VisionLine, _date_ru, _esc, _eye_mark, _p)

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
TOP_MM = 14.0
BOTTOM_MM = 18.0

TITLE = ParagraphStyle("dtitle", parent=BODY, fontName=FONT_BOLD, fontSize=17, leading=21, alignment=1)
SUB = ParagraphStyle("dsub", parent=BODY, fontName=FONT_SEMI, fontSize=10, leading=13, alignment=1)
TEXT = ParagraphStyle("dtext", parent=BODY, fontSize=9.5, leading=13.2)
HEAD = ParagraphStyle("dhead", parent=TEXT, fontName=FONT_SEMI, fontSize=10, leading=14, spaceBefore=5, spaceAfter=1)


def full_date(iso: str | None) -> str:
    """«31» октября 2026 г. — as 2.9 dated the signatures."""
    d = date.fromisoformat(iso[:10]) if iso else date.today()
    return f"«{d.day:02d}» {MONTHS[d.month - 1]} {d.year} г."


def stayed(patronymic: str) -> str:
    p = (patronymic or "").strip().lower()
    if p.endswith(("вна", "чна", "кызы")):
        return "Находилась"
    if p.endswith(("вич", "ич", "оглы")):
        return "Находился"
    return "Находился(лась)"


class Signatures(Flowable):
    """The date on the left, the signature lines stacked on the right."""

    LINE = 42 * mm

    def __init__(self, date_text: str, labels: list[str]):
        super().__init__()
        self.date_text, self.labels = date_text, labels

    def wrap(self, aw, ah):
        self.width = aw
        self.height = 8 + 9 * mm * len(self.labels)
        return aw, self.height

    def draw(self):
        c = self.canv
        top = self.height - 4
        c.setFont(FONT, 9.5)
        c.drawString(0, top - 9 * mm + 4, self.date_text)
        for i, label in enumerate(self.labels):
            y = top - 9 * mm * (i + 1) + 4
            c.setLineWidth(0.7)
            c.line(self.width - self.LINE, y - 1, self.width, y - 1)
            c.setFont(FONT, 9.5)
            c.drawRightString(self.width - self.LINE - 4, y, label)


def _box(rows: list[list], widths: list[float]) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.9, "black"), ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
        *[("LINEBELOW", (0, r), (-1, r), 0.4, "#c8c8c8") for r in range(len(rows) - 1)],
    ]))
    return t


def _label_cell(text: str):
    return _p(f"<font name='{FONT_SEMI}' color='{GREY}'>{_esc(text)}</font>", TEXT)


def _extra_lines(f: dict) -> list:
    """ВГД max/min, elastotonometry, Nesterov tonography — each only when filled in (as 2.9)."""
    rows = []
    if any(f[k] for k in ("vgd_od_max", "vgd_od_min", "vgd_os_max", "vgd_os_min")):
        rows.append(["ВГД", *[f"{e.upper()}  max {f[f'vgd_{e}_max'] or '—'}  min {f[f'vgd_{e}_min'] or '—'}  мм рт. ст."
                              for e in ("od", "os")]])
    if f["elasto_od"] or f["elasto_os"]:
        rows.append(["Эластотонометрия", f"OD  {f['elasto_od'] or '—'}", f"OS  {f['elasto_os'] or '—'}"])
    if any(f[f"tono_{e}_{k}"] for e in ("od", "os") for k in ("ro", "c", "kb", "f")):
        rows.append(["Тонография по Нестерову", *[
            f"{e.upper()}  Ро {f[f'tono_{e}_ro'] or '—'}  С {f[f'tono_{e}_c'] or '—'}  КБ {f[f'tono_{e}_kb'] or '—'}  F {f[f'tono_{e}_f'] or '—'}"
            for e in ("od", "os")]])
    if not rows:
        return []
    first = 52 * mm
    cells = [[_label_cell(a), _p(_esc(b), TEXT), _p(_esc(c), TEXT)] for a, b, c in rows]
    return [Spacer(0, 3), _box(cells, [first, (CONTENT_W - first) / 2, (CONTENT_W - first) / 2]), Spacer(0, 2)]


def _paras(text: str) -> list:
    return [_p(_esc(line), TEXT) for line in (text or "").strip().split("\n") if line.strip()] or [_p("&nbsp;", TEXT)]


def story(case: dict, f: dict, admission: dict | None, s: dict) -> list:
    out: list = [Spacer(0, 13 * mm),
                 _p(f"ВЫПИСКА{' № ' + _esc(case['medCard']) if case['medCard'] else ''}", TITLE),
                 _p("из медицинской карты стационарного больного", SUB), Spacer(0, 5 * mm)]

    first = 60 * mm
    rows = [
        ("В", f["destination"]),
        ("1. Фамилия, имя, отчество", case["patient"]),
        ("2. Дата рождения", _date_ru(case["dob"]) if case["dob"] else ""),
        ("3. Домашний адрес", case["address"]),
        ("4. Место работы и род занятий", f["workplace"]),
        ("5. Даты", f"поступления — {_date_ru(case['admittedAt']) if case['admittedAt'] else ''}, "
                    f"выписки — {_date_ru(f['discharge_date'])}"),
    ]
    cells = [[_label_cell(a), _p(f"<b>{_esc(b)}</b>" if a.startswith("1.") else _esc(b) or "&nbsp;", TEXT)] for a, b in rows]
    out += [_box(cells, [first, CONTENT_W - first]), Spacer(0, 4 * mm)]

    out.append(_p("6. Полный диагноз (основное заболевание, сопутствующее осложнение)", HEAD))
    dx = Table([[_p(f"<b>{_esc(f['final_diagnosis']) or '&nbsp;'}</b>", TEXT)]], colWidths=[CONTENT_W], hAlign="LEFT")
    dx.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.1, "black"), ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5)]))
    out += [Spacer(0, 1), dx, Spacer(0, 2 * mm)]

    out.append(_p("7. Эпикриз", HEAD))
    department = (s["department"] or "офтальмологическом отделении").strip()
    where = department[0].lower() + department[1:] if department else ""
    if where.endswith("отделение"):
        where = where[: -len("отделение")] + "отделении"
    where = where.replace("ое отделении", "ом отделении")
    out.append(_p(f"{stayed(case['patronymic'])} на стационарном лечении в {_esc(where)}.", TEXT))
    eyes = vision_of(admission) if admission else None
    if eyes:
        out += [_p("<b>При поступлении:</b>", TEXT), VisionLine(eyes)]
    out += _paras(f["epicrisis"])
    out += _extra_lines(f)
    if f["treatment_summary"].strip():
        out.append(_p(f"<font name='{FONT_SEMI}'>Лечение:</font> {_esc(f['treatment_summary'])}", TEXT))
    eyes = vision_of(f)
    if eyes:
        out += [Spacer(0, 2), _p("<b>При выписке:</b>", TEXT), VisionLine(eyes)]

    out += [Spacer(0, 2 * mm), _p("8. Лечебные и трудовые рекомендации", HEAD), *_paras(f["recommendations"])]

    labels = [*(["Зам. главного врача"] if f["sig_dep_chief"] else []), *(["Главный врач"] if f["sig_chief"] else []),
              "Зав. отделением"]
    out += [Spacer(0, 6 * mm), KeepTogether([Signatures(full_date(f["discharge_date"]), labels)])]
    return out


def _page(case: dict, s: dict):
    org = [ln.strip() for ln in s["org_header"].splitlines() if ln.strip()]

    def draw(c, doc):
        top = PAGE_H - TOP_MM * mm
        if doc.page == 1:
            _eye_mark(c, MARGIN_X, top - 4 * mm)
            tx = MARGIN_X + 11.5 * mm
            c.setFont(FONT_SEMI, 8.5)
            for i, line in enumerate(org):
                c.drawString(tx, top - 2.6 * mm - i * 3.8 * mm, line)
            c.setFillColor(GREY)
            c.setFont(FONT, 8)
            c.drawRightString(PAGE_W - MARGIN_X, top - 2.6 * mm, s["department"] or "")
            c.drawRightString(PAGE_W - MARGIN_X, top - 6.4 * mm, f"история болезни № {case['number']}")
            c.setFillColor("black")
        c.setFillColor(GREY)
        c.setFont(FONT, 7.5)
        c.drawString(MARGIN_X, 10 * mm, f"{case['patient']} · выписка")
        c.drawRightString(PAGE_W - MARGIN_X, 10 * mm, f"стр. {doc.page}")
        c.setFillColor("black")
    return draw


def pdf(conn: sqlite3.Connection, case_id: str) -> bytes:
    f = dis.saved(conn, case_id)
    if f is None:
        raise dis.DischargeError(404, "Выписка ещё не оформлена")
    d = dis.draft(conn, case_id)
    case = {**d["case"], "patronymic": conn.execute(
        "SELECT p.patronymic FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.id = ?",
        (case_id,)).fetchone()["patronymic"]}
    s = settings.get(conn)
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                          topMargin=TOP_MM * mm, bottomMargin=BOTTOM_MM * mm,
                          title=f"Выписка — {case['patient']}", author="MedQT")
    frame = Frame(MARGIN_X, BOTTOM_MM * mm, CONTENT_W, PAGE_H - (TOP_MM + BOTTOM_MM) * mm,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=_page(case, s))])
    doc.build(story(case, f, d["sources"]["admissionVision"], s))
    return buf.getvalue()


@printjobs._serialized
def preview_png(conn: sqlite3.Connection, case_id: str, page: int, dpi: int = 110) -> tuple[bytes, int]:
    """One page as PNG, and how many pages there are."""
    import pypdfium2

    doc = pypdfium2.PdfDocument(pdf(conn, case_id))
    if not 1 <= page <= len(doc):
        raise dis.DischargeError(404, "Нет такой страницы")
    out = io.BytesIO()
    doc[page - 1].render(scale=dpi / 72).to_pil().convert("RGB").save(out, "PNG")
    return out.getvalue(), len(doc)


@printjobs._serialized
def pages(conn: sqlite3.Connection, case_id: str) -> int:
    import pypdfium2

    return len(pypdfium2.PdfDocument(pdf(conn, case_id)))


def send(conn: sqlite3.Connection, case_id: str, printer: str, copies: int = 1, output_file: str | None = None) -> None:
    from . import winprint

    data = pdf(conn, case_id)
    for _ in range(max(1, min(copies, 5))):
        winprint.print_pdf(data, printer, f"MedQT — выписка ({date.today():%d.%m.%Y})", output_file)
