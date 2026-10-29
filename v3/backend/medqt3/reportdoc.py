"""The department report as a Word file (.docx) in the department's own form, ready to be edited:
the tables are filled in, the text parts (staff, equipment, conclusions) are left to the doctor.

A .docx is a zip of a few XML files; the handful of elements needed here (paragraphs, tables with
merged header cells) are written directly, so the program needs no extra library.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

FONT = "Times New Roman"
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь",
          "декабрь"]

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>"""


def _run(text: str, bold: bool = False, size: int = 12) -> str:
    rpr = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>' + ("<w:b/>" if bold else "") + \
          f'<w:sz w:val="{size * 2}"/><w:szCs w:val="{size * 2}"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(text: str = "", bold: bool = False, size: int = 12, align: str = "left", after: int = 6) -> str:
    return (f'<w:p><w:pPr><w:spacing w:before="0" w:after="{after * 20}"/><w:jc w:val="{align}"/></w:pPr>'
            f"{_run(text, bold, size) if text else ''}</w:p>")


def table(rows: list[list], widths: list[int], header_rows: int = 1) -> str:
    """rows: cells are str, or (str, {"span": n}) / (str, {"vmerge": "restart"|"continue"}). widths in mm."""
    tw = [int(w * 56.7) for w in widths]           # mm -> twentieths of a point
    border = "".join(f'<w:{b} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                     for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{sum(tw)}" w:type="dxa"/><w:tblBorders>{border}</w:tblBorders>'
           '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="70" w:type="dxa"/><w:right w:w="70" w:type="dxa"/>'
           '</w:tblCellMar></w:tblPr><w:tblGrid>' + "".join(f'<w:gridCol w:w="{w}"/>' for w in tw) + "</w:tblGrid>"]
    for ri, row in enumerate(rows):
        head = ri < header_rows
        out.append("<w:tr>" + ('<w:trPr><w:tblHeader/></w:trPr>' if head else ""))
        col = 0
        for cell in row:
            text, opt = (cell if isinstance(cell, tuple) else (cell, {}))
            span = opt.get("span", 1)
            w = sum(tw[col:col + span])
            pr = f'<w:tcW w:w="{w}" w:type="dxa"/>' + (f'<w:gridSpan w:val="{span}"/>' if span > 1 else "")
            if "vmerge" in opt:
                pr += '<w:vMerge w:val="restart"/>' if opt["vmerge"] == "restart" else "<w:vMerge/>"
            align = "left" if col == 0 or (col == 1 and opt.get("left")) else "center"
            out.append(f"<w:tc><w:tcPr>{pr}<w:vAlign w:val=\"center\"/></w:tcPr>"
                       f"{para(str(text), bold=head or opt.get('bold', False), size=11, align=align, after=0)}</w:tc>")
            col += span
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def build(body: list[str]) -> bytes:
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) +
           '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1418" w:header="709" w:footer="709" w:gutter="0"/>'
           "</w:sectPr></w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


# ---------- the report ----------

def period_title(lo: str, hi: str) -> str:
    """«2025 год», «1 полугодие 2026 г.», «3 квартал 2026 г.», «октябрь 2026 г.» or the dates."""
    a, b = date.fromisoformat(lo), date.fromisoformat(hi)
    month_end = lambda d: (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)  # noqa: E731
    if a.year == b.year and a.day == 1 and b == month_end(b):
        if (a.month, b.month) == (1, 12):
            return f"{a.year} год"
        if (a.month, b.month) in ((1, 6), (7, 12)):
            return f"{1 if a.month == 1 else 2} полугодие {a.year} г."
        if b.month - a.month == 2 and a.month % 3 == 1:
            return f"{a.month // 3 + 1} квартал {a.year} г."
        if a.month == b.month:
            return f"{MONTHS[a.month - 1]} {a.year} г."
    return f"период с {a:%d.%m.%Y} по {b:%d.%m.%Y}"


def _department_genitive(name: str) -> str:
    """«Офтальмологическое отделение» -> «офтальмологического отделения» (the usual form of the name)."""
    words = name.strip().split()
    if len(words) == 2 and words[0].lower().endswith("ое") and words[1].lower() == "отделение":
        return f"{words[0][:-2].lower()}ого отделения"
    return f"отделения «{name.strip()}»" if name.strip() else "отделения"


def _n(v) -> str:
    """Numbers as the reports write them: «-» for nothing, a comma for decimals."""
    if v is None or v == 0:
        return "-"
    if isinstance(v, float):
        return (f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))).replace(".", ",")
    return str(v)


def document(data: dict, department: str) -> bytes:
    cur, prev = data["current"], data["previous"]
    p = prev if prev["hasData"] else None          # no data for last year: the doctor fills that column in
    pv = (lambda f: _n(f(p)) if p else "")
    title_cur, title_prev = period_title(cur["from"], cur["to"]), period_title(prev["from"], prev["to"])
    y_cur, y_prev = cur["to"][:4], prev["to"][:4]
    body = [para(f"Отчёт {_department_genitive(department)} за {title_cur}", bold=True, size=14, align="center", after=10)]

    cm, pm = cur["main"], (p or {}).get("main", {})
    ch_cur = {c["label"]: c["count"] for c in cur["channels"]}
    ch_prev = {c["label"]: c["count"] for c in (p or {}).get("channels", [])}
    sc, sp = cur["surgery"], (p or {}).get("surgery", {})

    def m(key):
        return [pv(lambda x: x["main"][key]), _n(cm[key])]

    rows = [
        ("Количество сметных коек", [pv(lambda x: x["main"]["beds"]), _n(cm["beds"])]),
        ("Пролечено больных", m("treated")),
        ("   из них сельских", m("rural")),
        ("   из них иногородних", m("nonresident")),
        ("   из них иностранных граждан", m("foreign")),
        ("   из них подростки", m("teens")),
        ("   из них дети", m("children")),
        ("Поступило больных", m("admitted")),
        ("Выписано больных", m("discharged")),
        ("Проведено койко-дней", m("bedDays")),
        ("Средняя длительность пребывания больного на койке", m("avgStay")),
        ("Средний оборот койки", m("turnover")),
        ("Среднее число дней работы койки", m("bedWork")),
        ("Среднее время простоя койки", m("bedIdle")),
        ("Процент госпитализации сельских жителей", m("ruralPercent")),
        ("Процент выполнения плана койко-дней", m("planPercent")),
        ("Госпитализированы экстренно", m("emergency")),
        *[(f"   {k}", [_n(ch_prev.get(k)) if p else "", _n(ch_cur.get(k))]) for k, kind in
          ((c["label"], c["kind"]) for c in cur["channels"]) if kind == "emergency"],
        ("Госпитализированы планово", m("planned")),
        *[(f"   {k}", [_n(ch_prev.get(k)) if p else "", _n(ch_cur.get(k))]) for k, kind in
          ((c["label"], c["kind"]) for c in cur["channels"]) if kind == "planned"],
        ("Количество прооперированных больных", [_n(sp.get("operatedUrgent", 0) + sp.get("operatedPlanned", 0)) if p else "",
                                                  _n(sc["operatedUrgent"] + sc["operatedPlanned"])]),
        ("   в срочном порядке", [_n(sp.get("operatedUrgent")) if p else "", _n(sc["operatedUrgent"])]),
        ("   в плановом порядке", [_n(sp.get("operatedPlanned")) if p else "", _n(sc["operatedPlanned"])]),
        ("Количество операций", [_n(sp.get("operations")) if p else "", _n(sc["operations"])]),
        ("   в срочном порядке", [_n(sp.get("urgent")) if p else "", _n(sc["urgent"])]),
        ("   в плановом порядке", [_n(sp.get("planned")) if p else "", _n(sc["planned"])]),
        ("Послеоперационные осложнения: операция экстренная", [_n(sp.get("complicationsUrgent")) if p else "", _n(sc["complicationsUrgent"])]),
        ("Послеоперационные осложнения: операция плановая", [_n(sp.get("complicationsPlanned")) if p else "", _n(sc["complicationsPlanned"])]),
        ("Умерло всего", m("died")),
    ]
    body.append(para("Основные показатели работы отделения", bold=True, align="center", after=4))
    body.append(table([["№", "Показатели", y_prev, y_cur]] + [[str(i), (label, {"left": True}), *vals]
                                                              for i, (label, vals) in enumerate(rows, 1)],
                      [10, 110, 25, 25]))

    outcomes = cur["outcomes"]
    if outcomes:
        body.append(para("", after=0))
        body.append(para("Из выписанных больных:", bold=True, after=2))
        body += [para(f"{o['label']} — {o['count']}", after=0) for o in outcomes]

    def nested(title: str, first: str, items_cur: list, items_prev: list | None, count_label: str) -> None:
        body.append(para("", after=0))
        body.append(para(title, bold=True, align="center", after=4))
        head1 = [(first, {"vmerge": "restart"}), (count_label, {"span": 2}), ("Удельный вес", {"span": 2}),
                 ("Проведено к-дней", {"span": 2}), ("Среднее пребывание б-го на койке", {"span": 2})]
        head2 = [("", {"vmerge": "continue"})] + [y for _ in range(4) for y in (y_prev, y_cur)]
        prev_by = {x["label"]: x for x in (items_prev or [])}
        rows = []
        for x in items_cur:
            q = prev_by.get(x["label"])
            pick = (lambda k: _n(q[k]) if q else "")
            rows.append([x["label"], pick("count"), _n(x["count"]), pick("share"), _n(x["share"]),
                         pick("bedDays"), _n(x["bedDays"]), pick("avgStay"), _n(x["avgStay"])])
        tot = lambda items: (sum(x["count"] for x in items), sum(x["bedDays"] for x in items))  # noqa: E731
        c_n, c_bd = tot(items_cur)
        total = ["Итого:"]
        if items_prev is not None:
            p_n, p_bd = tot(items_prev)
            total += [_n(p_n), _n(c_n), "100" if p_n else "-", "100" if c_n else "-", _n(p_bd), _n(c_bd),
                      _n(round(p_bd / p_n, 2) if p_n else None), _n(round(c_bd / c_n, 2) if c_n else None)]
        else:
            total += ["", _n(c_n), "", "100" if c_n else "-", "", _n(c_bd), "", _n(round(c_bd / c_n, 2) if c_n else None)]
        rows.append([(total[0], {"bold": True})] + [(v, {"bold": True}) for v in total[1:]])
        body.append(table([head1, head2] + rows, [52] + [15] * 8, header_rows=2))

    # «за 2025-2026 годы», «за 1 полугодие 2025-2026 гг.» — both years, as the department writes it.
    part = title_cur.replace(f" {y_cur} г.", "").replace(f"{y_cur} год", "").strip()
    both = f"{y_prev}-{y_cur} годы" if not part else f"{part} {y_prev}-{y_cur} гг."
    nested(f"Структура пролеченных больных за {both}" if not title_cur.startswith("период") else
           f"Структура пролеченных больных за {title_cur}", "Наименование",
           cur["structure"], p["structure"] if p else None, "Выписано больных")
    nested(f"Операции за {title_cur}", "Наименование", cur["operations"], p["operations"] if p else None,
           "Количество операций")

    body.append(para("", after=0))
    body.append(para("Таблицы заполнены программой MedQT по историям болезни. Штаты, оборудование, платные услуги "
                     "и выводы допишите вручную.", size=10, after=0))
    return build(body)


def file_name(lo: str, hi: str) -> str:
    t = period_title(lo, hi).replace(" ", "_").replace(".", "")
    return f"otchet_{lo}_{hi}.docx" if t.startswith("период") else f"Отчёт_отделения_{t}.docx"
