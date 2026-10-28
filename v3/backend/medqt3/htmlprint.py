"""Print the HTML that 2.9 stored for a record (primary exams) as PDF flowables.

2.9 printed these records straight from their saved HTML, and that is the text the
doctor reviewed and signed, so v3 prints the same HTML. It uses a small, fixed set
of markup: div/p/span/b/u/br and tables — Vis/ВГД fractions are nested borderless
tables with a bottom border on the upper cell, the local status is a bordered table —
plus an embedded <style> with `.title { font-weight: 700 }` and the body font size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from .printlayout import CONTENT_W, FONT, FONT_BOLD, FONT_SIZE

BLOCK = {"div", "p", "table", "tr", "td", "th", "body", "html", "h1", "h2", "h3", "h4", "ul", "ol", "li"}
SKIP = {"head", "script", "title", "meta"}
VOID = {"br", "meta", "img", "hr", "col"}
ALIGN = {"center": TA_CENTER, "right": TA_RIGHT, "left": TA_LEFT}
BOLD = ("bold", "600", "700", "800")


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)   # Node or str


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.skip = 0
        self.in_style = False
        self.css = []

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self.in_style = True
            return
        if tag in SKIP:
            if tag not in VOID:
                self.skip += 1
            return
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
            return
        if tag in SKIP:
            if tag not in VOID:
                self.skip = max(0, self.skip - 1)
            return
        for i in range(len(self.stack) - 1, 0, -1):   # tolerate unclosed tags
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.in_style:
            self.css.append(data)
        elif not self.skip:
            self.stack[-1].children.append(data)


def _decls(text: str) -> dict:
    out = {}
    for decl in text.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip().lower()] = v.strip().lower()
    return out


@dataclass
class Ctx:
    """Font size of this record and the class rules from its embedded <style>."""
    size: float = FONT_SIZE
    classes: dict = field(default_factory=dict)

    @property
    def leading(self) -> float:
        return self.size * 1.25

    def style(self, node: Node) -> dict:
        out = {}
        for cls in node.attrs.get("class", "").split():
            out.update(self.classes.get(cls, {}))
        out.update(_decls(node.attrs.get("style", "")))
        return out

    def bold(self, node: Node) -> bool:
        return node.tag in ("b", "strong", "th") or self.style(node).get("font-weight") in BOLD

    def para_style(self, align=TA_LEFT, bold=False) -> ParagraphStyle:
        return ParagraphStyle("h", fontName=FONT_BOLD if bold else FONT, fontSize=self.size,
                              leading=self.leading, alignment=align)


def _ctx(css: str) -> Ctx:
    ctx = Ctx()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        decls = _decls(body)
        for sel in (s.strip() for s in selectors.split(",")):
            if sel == "body":
                m = re.match(r"([\d.]+)pt", decls.get("font-size", ""))
                if m:
                    ctx.size = float(m.group(1))
            elif re.fullmatch(r"\.[\w-]+", sel):
                ctx.classes.setdefault(sel[1:], {}).update(decls)
    return ctx


# ---------- inline text ----------

def _inline(ctx: Ctx, node, out: list[str]) -> None:
    if isinstance(node, str):
        out.append(escape(re.sub(r"\s+", " ", node)))
        return
    if node.tag == "br":
        out.append("<br/>")
        return
    st = ctx.style(node)
    wrap = []
    if ctx.bold(node):
        wrap.append("b")
    if node.tag == "u" or "underline" in st.get("text-decoration", ""):
        wrap.append("u")
    if node.tag in ("i", "em"):
        wrap.append("i")
    out.extend(f"<{w}>" for w in wrap)
    for ch in node.children:
        _inline(ctx, ch, out)
    out.extend(f"</{w}>" for w in reversed(wrap))


def _is_inline(node) -> bool:
    return isinstance(node, str) or node.tag not in BLOCK


def _text_lines(node) -> list[str]:
    def text(n):
        if isinstance(n, str):
            return n
        if n.tag == "br":
            return "\n"
        if n.tag == "table":
            return ""
        return "".join(text(c) for c in n.children)
    return [re.sub(r"\s+", " ", ln).strip() for ln in text(node).split("\n")]


def _para(ctx: Ctx, parts: list[str], align=TA_LEFT, bold=False) -> Paragraph | None:
    markup = "".join(parts).strip()
    markup = re.sub(r"^(<br/>\s*)+|(\s*<br/>)+$", "", markup)
    if not re.sub(r"<[^>]+>|\s", "", markup):
        return None
    return Paragraph(markup, ctx.para_style(align, bold))


# ---------- tables ----------

def _rows(table: Node) -> list[list[Node]]:
    rows = []

    def walk(n):
        for c in n.children:
            if isinstance(c, str):
                continue
            if c.tag == "tr":
                rows.append([x for x in c.children if not isinstance(x, str) and x.tag in ("td", "th")])
            elif c.tag in ("tbody", "thead", "tfoot"):
                walk(c)
    walk(table)
    return [r for r in rows if r]


def _pad(ctx: Ctx, cell: Node, table: Node) -> float:
    """Horizontal cell padding in points; "0 5px" means 0 vertical, 5px horizontal."""
    values = re.findall(r"([\d.]+)(?:px)?", ctx.style(cell).get("padding", ""))
    if values:
        return float(values[1] if len(values) > 1 else values[0]) * 0.75   # CSS px -> pt
    try:
        return float(table.attrs.get("cellpadding", "1")) * 0.6
    except ValueError:
        return 1.0


def _natural_width(ctx: Ctx, node) -> float:
    """Width the content needs without wrapping; bold font is assumed, so short cells never break."""
    if isinstance(node, str):
        return pdfmetrics.stringWidth(node.strip(), FONT_BOLD, ctx.size)
    if node.tag == "table":
        rows = _rows(node)
        if not rows:
            return 0
        widths = [0.0] * max(len(r) for r in rows)
        for r in rows:
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], _natural_width(ctx, cell) + 2 * _pad(ctx, cell, node) + 1)
        return sum(widths)
    text_w = max((pdfmetrics.stringWidth(ln, FONT_BOLD, ctx.size) for ln in _text_lines(node)), default=0)
    inner = [_natural_width(ctx, c) for c in node.children if not isinstance(c, str) and c.tag == "table"]
    return max([text_w] + inner)


def _table(ctx: Ctx, node: Node, avail: float) -> Flowable | None:
    rows = _rows(node)
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    bordered = node.attrs.get("border", "0") not in ("", "0")
    natural = [0.0] * ncol
    for r in rows:
        for i, cell in enumerate(r):
            natural[i] = max(natural[i], _natural_width(ctx, cell) + 2 * _pad(ctx, cell, node) + 1)
    if sum(natural) <= avail and not bordered:
        widths = natural
    elif ncol == 1:
        widths = [avail]
    else:  # a data table (local status): the first column as needed, the rest share the width
        first = min(natural[0], avail * 0.28)
        widths = [first] + [(avail - first) / (ncol - 1)] * (ncol - 1)

    data, cmds = [], [("VALIGN", (0, 0), (-1, -1), "TOP")]
    for ri, r in enumerate(rows):
        row = []
        for ci in range(ncol):
            if ci >= len(r):
                row.append("")
                continue
            cell = r[ci]
            st = ctx.style(cell)
            pad = _pad(ctx, cell, node)
            align = ALIGN.get(st.get("text-align") or cell.attrs.get("align", "left"), TA_LEFT)
            row.append(blocks(ctx, cell, widths[ci] - 2 * pad, align, bold=cell.tag == "th") or "")
            vpad = 1.5 if bordered else 0.8
            cmds += [("LEFTPADDING", (ci, ri), (ci, ri), pad), ("RIGHTPADDING", (ci, ri), (ci, ri), pad),
                     ("TOPPADDING", (ci, ri), (ci, ri), vpad), ("BOTTOMPADDING", (ci, ri), (ci, ri), vpad + 0.5)]
            if st.get("vertical-align") == "middle":
                cmds.append(("VALIGN", (ci, ri), (ci, ri), "MIDDLE"))
            line = st.get("border-bottom", "")
            if (line and "none" not in line) or st.get("border-bottom-style") == "solid":
                cmds.append(("LINEBELOW", (ci, ri), (ci, ri), 0.6, "black"))
        data.append(row)
    if bordered:
        cmds.append(("GRID", (0, 0), (-1, -1), 0.4, "black"))
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle(cmds))
    return t


# ---------- blocks ----------

def blocks(ctx: Ctx, node: Node, avail: float = CONTENT_W, align=TA_LEFT, bold: bool = False) -> list[Flowable]:
    """Flowables for the children of `node`: inline runs become paragraphs, tables become tables."""
    out: list[Flowable] = []
    run: list[str] = []
    st = ctx.style(node)
    own_align = ALIGN.get(st.get("text-align") or node.attrs.get("align", ""), align)

    def flush():
        p = _para(ctx, run, own_align, bold)
        if p:
            out.append(p)
        run.clear()

    for ch in node.children:
        if _is_inline(ch):
            _inline(ctx, ch, run)
            continue
        flush()
        if ch.tag == "table":
            t = _table(ctx, ch, avail)
            if t:
                out += [Spacer(0, 0.6 * mm), t, Spacer(0, 0.6 * mm)]
        else:
            out.extend(blocks(ctx, ch, avail, own_align, bold))
            if "section" in ch.attrs.get("class", "").split():
                out.append(Spacer(0, 1 * mm))
    flush()
    return out


def flowables(html: str) -> list[Flowable]:
    tree = _Tree()
    tree.feed(html or "")
    tree.close()
    return blocks(_ctx("".join(tree.css)), tree.root)
