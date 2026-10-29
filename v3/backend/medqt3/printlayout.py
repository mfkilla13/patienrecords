"""PDF layout for case records, continued on a partly used sheet.

Look: «В стиле программы» — Onest, black only (the printer is a b/w laser):
a sheet heading (department + patient box) and a footer «лист N» are printed only
when a new sheet starts; every record opens with its date in a rounded frame.

A print starts `start_mm` below the top edge of the paper on the first page and at
CONTENT_TOP_MM (under the sheet heading) on the following pages. After building,
we know exactly where each record lies, so the next print continues right below it.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from html import escape
from pathlib import Path

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

from . import exam as exam_mod
from .clinical import _treatment_lines, vision as vision_of
from .importer import to_date

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
SHEET_TOP_MM = 13.0         # sheet heading starts here
CONTENT_TOP_MM = 37.0       # records on a new sheet start under the heading
MARGIN_TOP_MM = CONTENT_TOP_MM   # kept for callers: «top of a fresh sheet»
MARGIN_BOTTOM_MM = 20.0
FOOTER_MM = 287.0
GAP_MM = 1.5                # space between consecutive prints on one sheet
FONT_SIZE = 9
LEADING = 12.5
CONTENT_W = PAGE_W - 2 * MARGIN_X
LAST_LINE_MM = 297 - MARGIN_BOTTOM_MM
GREY = "#444444"
LIGHT = "#c8c8c8"

FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _register_fonts() -> tuple[str, str, str]:
    onest = [FONT_DIR / f"Onest-{w}.ttf" for w in ("Regular", "SemiBold", "Bold")]
    if all(p.exists() for p in onest):
        for name, path in zip(("Body", "Body-Semi", "Body-Bold"), onest):
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold")
        return "Body", "Body-Semi", "Body-Bold"
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")   # fallback: system Segoe UI
    for regular, bold in (("segoeui.ttf", "segoeuib.ttf"), ("arial.ttf", "arialbd.ttf")):
        r, b = os.path.join(fonts_dir, regular), os.path.join(fonts_dir, bold)
        if os.path.exists(r) and os.path.exists(b):
            pdfmetrics.registerFont(TTFont("Body", r))
            pdfmetrics.registerFont(TTFont("Body-Bold", b))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold")
            return "Body", "Body-Bold", "Body-Bold"
    raise RuntimeError("Не найден шрифт для печати.")


FONT, FONT_SEMI, FONT_BOLD = _register_fonts()
BODY = ParagraphStyle("body", fontName=FONT, fontSize=FONT_SIZE, leading=LEADING)
TITLE = ParagraphStyle("title", parent=BODY, fontName=FONT_BOLD, fontSize=9.5, leading=13)


def _p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text, style)


def _esc(text) -> str:
    return escape(str(text or "").strip()).replace("\n", "<br/>")


def _date_ru(value: str) -> str:
    """'2026-04-30...' or 2.9-style '30.04.2026' -> '30.04.2026'."""
    iso = to_date(value)
    if not iso:
        return str(value)
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def _record_date(data: dict, recorded_at: str) -> str:
    return _date_ru(data.get("date") if to_date(data.get("date")) else recorded_at)


def _record_time(data: dict, recorded_at: str) -> str:
    t = (data.get("time") or recorded_at[11:16] or "").strip()
    return "" if t in ("", "00:00") else t


# ---------- building blocks ----------

class RecordHead(Flowable):
    """The date in a rounded frame, then the kind of record and the time."""

    H = 15

    def __init__(self, date_text: str, kind: str, time: str = ""):
        super().__init__()
        self.date_text, self.kind, self.time = date_text, kind, time

    def wrap(self, aw, ah):
        return aw, self.H + 3

    def draw(self):
        c = self.canv
        y0 = 3
        dw = pdfmetrics.stringWidth(self.date_text, FONT_BOLD, 9) + 14
        c.setLineWidth(0.9)
        c.roundRect(0, y0, dw, self.H - 2, (self.H - 2) / 2, stroke=1, fill=0)
        c.setFont(FONT_BOLD, 9)
        c.drawString(7, y0 + 3.9, self.date_text)
        x = dw + 8
        c.setFont(FONT_SEMI, 9.5)
        c.drawString(x, y0 + 3.9, self.kind)
        if self.time:
            x += pdfmetrics.stringWidth(self.kind, FONT_SEMI, 9.5) + 7
            c.setFillColor(GREY)
            c.setFont(FONT, 8.5)
            c.drawString(x, y0 + 3.9, self.time)
            c.setFillColor("black")


class DashedRule(Flowable):
    """The dashed line that closes every record."""

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 7

    def draw(self):
        c = self.canv
        c.setStrokeColor("#9a9a9a")
        c.setLineWidth(0.6)
        c.setDash(2.2, 2)
        c.line(0, 1.5, self.width, 1.5)
        c.setDash()
        c.setStrokeColor("black")


class SignLine(Flowable):
    """«Петрова Е. В. ________» at the right edge (several signatures side by side)."""

    LINE = 38 * mm

    def __init__(self, *labels: str):
        super().__init__()
        self.labels = [lb for lb in labels]

    def wrap(self, aw, ah):
        self.width = aw
        return aw, 16

    def draw(self):
        c = self.canv
        x = self.width
        for label in reversed(self.labels):
            c.setLineWidth(0.7)
            c.line(x - self.LINE, 3, x, 3)
            x -= self.LINE + 4
            c.setFont(FONT, 8.5)
            w = pdfmetrics.stringWidth(label, FONT, 8.5)
            c.drawString(x - w, 4, label)
            x -= w + 14


def eye_vision(e: dict) -> str:
    """One eye as written by hand: «0,8 с коррекцией −1,5 D = 1,0», «0,1 n.k.», «счет пальцев у лица»."""
    parts = [x for x in (e["vis"], e["status"]) if x]
    if e["corr"] or e["result"]:
        parts.append("с коррекцией" + (f" {e['corr']}" if e["corr"] else "") + (f" = {e['result']}" if e["result"] else ""))
    return " ".join(parts) or "—"


class VisionLine(Flowable):
    """Vis OD/OS = a/b     ВГД OD/OS = c/d мм рт. ст. — drawn as fractions. With a correction or a status on
    either eye Vis is written per eye in two lines («OD = 0,8 с коррекцией −1,5 D = 1,0» / «OS = 0,9»): a fraction
    with blank halves reads as nonsense. Same height either way, so printed positions do not move."""

    PAD = 2.5
    SIZE = 9.5

    def __init__(self, eyes: dict):
        super().__init__()
        self.groups = self._groups(eyes)

    @staticmethod
    def _groups(e: dict) -> list[list]:
        od, os_ = e["od"], e["os"]
        groups = []
        if od["vis"] or os_["vis"]:
            if any(x[k] for x in (od, os_) for k in ("status", "corr", "result")):
                groups.append([("text", "Vis", True), ("rows", f"OD = {eye_vision(od)}", f"OS = {eye_vision(os_)}", False)])
            else:
                groups.append([("text", "Vis", True), ("frac", "OD", "OS", False), ("text", "=", False),
                               ("frac", od["vis"] or "—", os_["vis"] or "—", True)])
        if od["iop"] or os_["iop"]:
            groups.append([("text", "ВГД", True), ("frac", "OD", "OS", False), ("text", "=", False),
                           ("frac", od["iop"] or "—", os_["iop"] or "—", True), ("small", "мм рт. ст.", False)])
        return groups

    def _w(self, text: str, bold: bool, size: float | None = None) -> float:
        return pdfmetrics.stringWidth(text, FONT_BOLD if bold else FONT, size or self.SIZE)

    def _item_w(self, item) -> float:
        if item[0] == "text":
            return self._w(item[1], item[2])
        if item[0] == "small":
            return self._w(item[1], False, 8)
        return max(self._w(item[1], item[3]), self._w(item[2], item[3]), 6) + 2 * self.PAD

    def wrap(self, aw, ah):
        self.height = 2 * LEADING + 3
        return aw, self.height

    def draw(self):
        c = self.canv
        mid = self.height / 2
        x = 0.0
        for gi, group in enumerate(self.groups):
            if gi:
                x += 9 * mm
            for item in group:
                w = self._item_w(item)
                if item[0] in ("text", "small"):
                    size = 8 if item[0] == "small" else self.SIZE
                    c.setFont(FONT_BOLD if item[2] else FONT, size)
                    c.drawString(x, mid - size * 0.35, item[1])
                elif item[0] == "rows":
                    c.setFont(FONT, self.SIZE)
                    c.drawString(x + self.PAD, mid + 2.6, item[1])
                    c.drawString(x + self.PAD, mid - self.SIZE - 0.6, item[2])
                else:
                    c.setFont(FONT_BOLD if item[3] else FONT, self.SIZE)
                    c.drawCentredString(x + w / 2, mid + 2.6, item[1])
                    c.drawCentredString(x + w / 2, mid - self.SIZE - 0.6, item[2])
                    c.setLineWidth(0.7)
                    c.line(x + 1, mid + 0.9, x + w - 1, mid + 0.9)
                x += w + 4


class Marker(Flowable):
    """Zero-size flowable that records where it was drawn (page and mm from the top edge)."""

    def __init__(self, sink: dict, key: str):
        super().__init__()
        self.sink, self.key = sink, key

    def wrap(self, aw, ah):
        return 0, 0

    def draw(self):
        _, y = self.canv.absolutePosition(0, 0)
        self.sink[self.key] = (self.canv.getPageNumber(), round((PAGE_H - y) / mm, 2))


def _rounded_table(rows: list[list], widths: list[float], header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.9, "black"),
            ("ROUNDEDCORNERS", [5, 5, 5, 5]), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6)]
    if header:
        cmds.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, "black"))
        for r in range(1, len(rows) - 1):
            cmds.append(("LINEBELOW", (0, r), (-1, r), 0.4, LIGHT))
    t.setStyle(TableStyle(cmds))
    return t


def _label(name: str, text: str) -> Paragraph:
    return _p(f"<font name='{FONT_SEMI}'>{_esc(name)}:</font> {_esc(text)}")


# ---------- records ----------

def diary_block(data: dict, recorded_at: str, doctor: str) -> list:
    out: list = [RecordHead(_record_date(data, recorded_at), "Дневник", _record_time(data, recorded_at))]
    vitals = []
    if (data.get("bp") or "").strip():
        vitals.append(f"АД {_esc(data['bp'])} мм рт. ст.")
    if (data.get("hr") or "").strip():
        vitals.append(f"ЧСС {_esc(data['hr'])}")
    if (data.get("pulse") or "").strip():
        vitals.append(f"пульс {_esc(data['pulse'])} уд/мин")
    if (data.get("general_state") or "").strip():
        vitals.append(f"состояние {_esc(data['general_state'])}")
    if vitals:
        out.append(_p("&nbsp;&nbsp;·&nbsp;&nbsp;".join(vitals)))
    if (data.get("complaints") or "").strip():
        out.append(_label("Жалобы", data["complaints"]))
    eyes = vision_of(data)
    if eyes:
        out.append(VisionLine(eyes))
    for eye in ("OD", "OS", "OU"):
        if (data.get(f"{eye.lower()}_text") or "").strip():
            out.append(_label(eye, data[f"{eye.lower()}_text"]))
    treatment = " ".join(x for x in [(data.get("treatment") or "").strip(), ", ".join(_treatment_lines(data.get("basis")))] if x)
    if treatment:
        out.append(_label("Лечение", treatment))
    if (data.get("discharge_note") or "").strip():
        out.append(_p(_esc(data["discharge_note"])))
    out += [SignLine(doctor or "Подпись"), DashedRule()]
    return out


def protocol_block(data: dict, recorded_at: str, doctor: str) -> list:
    out: list = [RecordHead(_record_date(data, recorded_at), "Протокол операции", _record_time(data, recorded_at))]
    if (data.get("operation_name") or "").strip():
        out.append(_p(_esc(data["operation_name"]), TITLE))
    for para in (data.get("description") or "").strip().split("\n"):
        if para.strip():
            out.append(_p(_esc(para)))
    out += [SignLine(f"Хирург {doctor}".strip(), "Операционная сестра"), DashedRule()]
    return out


def text_block(data: dict, recorded_at: str, doctor: str) -> list:
    """A plain record from «Новая запись» (предоперационный эпикриз, консилиум, ...): its title, then the text."""
    out: list = [RecordHead(_record_date(data, recorded_at), (data.get("title") or "Запись").strip(), _record_time(data, recorded_at))]
    for para in (data.get("text") or "").strip().split("\n"):
        if para.strip():
            out.append(_p(_esc(para)))
    out += [SignLine(doctor or "Подпись"), DashedRule()]
    return out


def exam_block(raw: dict, recorded_at: str, doctor: str) -> list:
    """A primary exam written in v3, laid out like the other records."""
    d = exam_mod.complete(raw)
    out: list = [RecordHead(_date_ru(recorded_at), "Первичный осмотр", recorded_at[11:16] if recorded_at[11:16] not in ("", "00:00") else "")]
    if (d["complaints"] or "").strip():
        out.append(_label("Жалобы", d["complaints"]))
    anamnesis = " ".join(x for x in [(d["disease_anamnesis"] or "").strip().rstrip(".") + "." if (d["disease_anamnesis"] or "").strip() else "",
                                     f"Туберкулёз, кожвен-заболевания: {d['tb']}; аллергологический анамнез: "
                                     f"{exam_mod.allergy_text(d)}; страховой анамнез: {d['insurance']}."] if x)
    out.append(_label("Анамнез", anamnesis))
    out.append(_label("Объективно", " ".join(ln if ln.endswith(".") else f"{ln}." for ln in exam_mod.objective_lines(d))))
    eyes = vision_of(d)
    if eyes:
        out.append(VisionLine(eyes))
    rows = exam_mod.local_rows(d)
    if rows:
        cells = [[_p(f"<font name='{FONT_SEMI}'>Структура</font>"), _p(f"<font name='{FONT_SEMI}'>OD</font>"), _p(f"<font name='{FONT_SEMI}'>OS</font>")]]
        cells += [[_p(f"<font name='{FONT_SEMI}'>{_esc(n)}</font>"), _p(_esc(od)), _p(_esc(os_))] for n, od, os_ in rows]
        first = 36 * mm
        out += [Spacer(0, 2), _rounded_table(cells, [first, (CONTENT_W - first) / 2, (CONTENT_W - first) / 2]), Spacer(0, 4)]
    dx = exam_mod.diagnosis_text(d) or "не указан"
    box = Table([[_p(f"{_esc(d['diag_type']).capitalize()} диагноз: <b>{_esc(dx)}</b>")]],
                colWidths=[min(CONTENT_W, pdfmetrics.stringWidth(f"{d['diag_type']} диагноз: {dx}", FONT_BOLD, FONT_SIZE) + 18)], hAlign="LEFT")
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, "black"), ("ROUNDEDCORNERS", [5, 5, 5, 5]),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    out += [box, Spacer(0, 3)]
    if exam_mod.comorbid_text(d):
        out.append(_label("Сопутствующий", exam_mod.comorbid_text(d)))
    exams = [x for x in d["selected_examinations"] if x.strip()]
    if exams:
        out.append(_label("План обследования", ", ".join(exams)))
    lines = exam_mod.treatment_lines(d)
    if lines:
        out.append(_label("Обоснование лечения", "; ".join(f"{a} — {b}" for a, b in lines)))
    out += [SignLine(doctor or "Подпись"), DashedRule()]
    return out


def legacy_exam_block(html: str, recorded_at: str, doctor: str) -> list:
    """A primary exam written in 2.9: its saved text, under the same heading as other records."""
    from .htmlprint import flowables

    time = recorded_at[11:16] if recorded_at[11:16] not in ("", "00:00") else ""
    out = [RecordHead(_date_ru(recorded_at), "Первичный осмотр", time), *flowables(html)]
    if "______" not in html:   # 2.9 added the signature line when the saved text had none
        out.append(SignLine(doctor or "Подпись"))
    out.append(DashedRule())
    return out


# ---------- the sheet heading ----------

@dataclass
class SheetInfo:
    department: str
    org_line: str
    patient: str
    dob: str
    number: str
    admitted: str
    short: str          # «Тестова А. И. · история № 73» for the footer


def _eye_mark(c, x: float, y: float) -> None:
    r = 4.2 * mm
    c.setLineWidth(1.1)
    c.circle(x + r, y, r, stroke=1, fill=0)
    p = c.beginPath()   # the eye: two arcs and a pupil
    w, h = 2.6 * mm, 1.4 * mm
    p.moveTo(x + r - w, y)
    p.curveTo(x + r - w / 2, y + h * 1.3, x + r + w / 2, y + h * 1.3, x + r + w, y)
    p.curveTo(x + r + w / 2, y - h * 1.3, x + r - w / 2, y - h * 1.3, x + r - w, y)
    c.setLineWidth(0.9)
    c.drawPath(p, stroke=1, fill=0)
    c.circle(x + r, y, 0.75 * mm, stroke=1, fill=0)


def draw_sheet(c, info: SheetInfo, sheet_no: int) -> None:
    """Heading and footer of a fresh sheet."""
    top = PAGE_H - SHEET_TOP_MM * mm
    _eye_mark(c, MARGIN_X, top - 4 * mm)
    tx = MARGIN_X + 11.5 * mm
    c.setFont(FONT_BOLD, 11)
    c.drawString(tx, top - 3.4 * mm, info.department)
    c.setFillColor(GREY)
    c.setFont(FONT, 7.5)
    c.drawString(tx, top - 7.4 * mm, info.org_line)
    c.drawRightString(PAGE_W - MARGIN_X, top - 3 * mm, "Медицинская карта")
    c.drawRightString(PAGE_W - MARGIN_X, top - 6.4 * mm, "стационарного больного")
    c.setFillColor("black")

    by, bh = top - 19 * mm, 8.6 * mm
    c.setLineWidth(0.9)
    c.roundRect(MARGIN_X, by, CONTENT_W, bh, 3 * mm, stroke=1, fill=0)
    base = by + 3 * mm
    c.setFont(FONT_BOLD, 10.5)
    c.drawString(MARGIN_X + 4 * mm, base, info.patient)
    x = PAGE_W - MARGIN_X - 4 * mm
    for label, value in reversed([("д. р.", info.dob), ("история", f"№ {info.number}"), ("поступление", info.admitted)]):
        if not value or value == "№ ":
            continue
        c.setFont(FONT, 9)
        w = pdfmetrics.stringWidth(value, FONT, 9)
        c.drawString(x - w, base, value)
        x -= w + 3
        c.setFillColor(GREY)
        c.setFont(FONT, 7.5)
        lw = pdfmetrics.stringWidth(label, FONT, 7.5)
        c.drawString(x - lw, base, label)
        c.setFillColor("black")
        x -= lw + 8 * mm

    c.setFillColor(GREY)
    c.setFont(FONT, 7.5)
    fy = PAGE_H - FOOTER_MM * mm
    c.drawString(MARGIN_X, fy, info.short)
    c.drawRightString(PAGE_W - MARGIN_X, fy, f"лист {sheet_no}")
    c.setFillColor("black")


# ---------- layout ----------

@dataclass
class Place:
    """Where one record lies: PDF page (1-based) and mm from the paper's top edge, start and end."""
    start_page: int
    start_mm: float
    end_page: int
    end_mm: float


@dataclass
class Layout:
    pdf: bytes
    pages: int
    places: list[Place]

    @property
    def start_page(self) -> int:     # 2 if the first record did not fit on the first sheet
        return self.places[0].start_page

    @property
    def end_mm(self) -> float:       # where the last record ends on the last page
        return self.places[-1].end_mm


_FRAME_KW = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)


def _frame(top_mm: float, fid: str = "f") -> Frame:
    height = PAGE_H - top_mm * mm - MARGIN_BOTTOM_MM * mm
    return Frame(MARGIN_X, MARGIN_BOTTOM_MM * mm, CONTENT_W, max(height, 1), id=fid, **_FRAME_KW)


def build(blocks: list[list], start_mm: float, title: str = "MedQT") -> Layout:
    """Lay out record blocks one after another, the first page starting `start_mm` below the top edge
    and the following pages under the sheet heading. Each record is kept together on one sheet when
    it fits, and its exact place is recorded."""
    start_mm = max(start_mm, 5.0)
    sink: dict = {}
    story: list = [NextPageTemplate("rest")]
    for i, block in enumerate(blocks):
        items = ([Spacer(0, GAP_MM * mm)] if i else []) + [Marker(sink, f"s{i}")] + block + [Marker(sink, f"e{i}")]
        story.append(KeepTogether(items))

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, title=title, author="MedQT",
                          leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=CONTENT_TOP_MM * mm,
                          bottomMargin=MARGIN_BOTTOM_MM * mm)
    doc.addPageTemplates([PageTemplate("first", [_frame(start_mm, "first")]),
                          PageTemplate("rest", [_frame(CONTENT_TOP_MM, "rest")])])
    doc.build(story)
    places = [Place(*sink[f"s{i}"], *sink[f"e{i}"]) for i in range(len(blocks))]
    return Layout(pdf=buf.getvalue(), pages=places[-1].end_page, places=places)


def render_fixed(items: list[tuple[list, int, float]], info: SheetInfo | None = None,
                 new_sheets: set[int] | frozenset = frozenset(), title: str = "MedQT") -> tuple[bytes, list[int]]:
    """Draw each record at a known place: items are (block, sheet, start_mm), sorted by sheet and mm.

    Pages for sheets in `new_sheets` get the sheet heading and footer. Returns the PDF and the sheet
    number of every page. A record that ran over to the next sheet continues there under the heading.
    """
    from reportlab.pdfgen.canvas import Canvas

    buf = io.BytesIO()
    canv = Canvas(buf, pagesize=A4)
    canv.setTitle(title)
    canv.setAuthor("MedQT")
    sheets: list[int] = []

    def new_page(sheet: int) -> None:
        if sheets:
            canv.showPage()
        sheets.append(sheet)
        if info and sheet in new_sheets:
            draw_sheet(canv, info, sheet)

    for block, sheet, start_mm in items:
        if not sheets or sheets[-1] != sheet:
            if sheets and sheet < sheets[-1]:
                raise ValueError("records must be sorted by sheet")
            new_page(sheet)
        frame = _frame(start_mm)
        pending = list(block)
        fresh = False
        while pending:
            flowable = pending.pop(0)
            if frame.add(flowable, canv):
                fresh = False
                continue
            parts = frame.split(flowable, canv)
            if len(parts) > 1 and frame.add(parts[0], canv):
                pending = parts[1:] + pending
            elif fresh:
                raise ValueError("запись не помещается даже на целый лист")
            else:
                pending.insert(0, flowable)
            new_page(sheets[-1] + 1)
            frame = _frame(CONTENT_TOP_MM)
            fresh = True
    canv.showPage()
    canv.save()
    return buf.getvalue(), sheets
