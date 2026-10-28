"""Primary exam: the 2.9 form data (schema primary_exam_v1), norms, and its printed HTML.

The printed text is built exactly the way 2.9 built it in save_primary_exam(), so a
primary exam written in v3 looks on paper the same as one written in 2.9 (and is
printed through the same HTML path). User text is escaped; 2.9 did not.
"""

from __future__ import annotations

import copy
import json
import re
from html import escape

from .clinical import TREATMENT_LABELS

# Structures of the local status, in 2.9's order, with their options (windows/config.py).
LOCAL_OPTIONS: dict[str, list[str] | None] = {
    "Веки": ["без особенностей", "птоз", "отёк", "гиперемия края век", "блефарит", "заворот", "выворот",
             "светобоязнь", "слезотечение", "другое"],
    "Конъюнктива": ["бледно-розовая", "гиперемия", "отёк", "фолликулы", "папиллы", "кровоизлияния",
                    "отделяемое слизистое", "отделяемое гнойное", "другое"],
    "Склера/эписклера": ["без особенностей", "инъекция перикорнеальная", "инъекция эписклеральная",
                         "застойная инъекция", "желтушность", "другое"],
    "Роговица": ["прозрачная", "отёк", "эрозия", "инфильтрат", "помутнение", "инородное тело",
                 "неоваскуляризация", "другое"],
    "Передняя камера": None,   # depth + fluid, see ANTERIOR
    "Зрачок": ["круглый", "узкий", "широкий", "неправильной формы", "анизокория", "реакция снижена",
               "реакция отсутствует", "другое"],
    "Радужка": ["рисунок чёткий", "рисунок стушёванный", "атрофия", "дефекты", "пигментная кайма изменена", "другое"],
    "Хрусталик": ["прозрачный", "полупрозрачный", "неравномерно мутный", "гомогенно мутный", "молочного цвета"],
    "Стекловидное тело": ["не просматривается", "прозрачное", "плавающие помутнения", "деструкция", "кровоизлияние",
                          "шварты", "другое"],
    "Глазное дно": ["не просматривается", "ДЗН бледно-розовый", "ДЗН бледный", "ДЗН гиперемирован",
                    "с задней стафиломой", "контуры чёткие", "контуры стушёванные", "экскавация физиологическая",
                    "экскавация глаукоматозная", "макула без особенностей", "макула отёк", "макула дистрофия",
                    "кровоизлияния", "другое"],
    "Сосуды": ["не просматривается", "артерии в норме", "артерии сужены", "спазм артерий", "вены полнокровные",
               "вены расширены", "вены извитые", "A/V перекрёсты", "Salus I", "Salus II", "Salus III",
               "очаги кровоизлияния", "ишемии", "дегенеративные очаги", "другое"],
    "Сетчатка": ["не просматривается", "прилежит", "истончена", "разрыв (верхний квадрант)",
                 "разрыв (нижний квадрант)", "разрыв (височный)", "разрыв (носовой)", "отслойка", "другое"],
}
ANTERIOR = "Передняя камера"
ANTERIOR_OPTIONS = {"depth": ["нормальная", "мелкая", "глубокая"],
                    "fluid": ["прозрачная", "мутная", "гифема", "гипопион", "фибрин"]}

# «OD/OS норма» in 2.9.
NORMS = {
    "Веки": ["без особенностей"], "Конъюнктива": ["бледно-розовая"], "Склера/эписклера": ["без особенностей"],
    "Роговица": ["прозрачная"], "Зрачок": ["круглый"], "Радужка": ["рисунок чёткий"], "Хрусталик": ["прозрачный"],
    "Стекловидное тело": ["прозрачное"], "Глазное дно": ["ДЗН бледно-розовый", "контуры чёткие", "макула без особенностей"],
    "Сосуды": ["артерии в норме"], "Сетчатка": ["прилежит"],
}
ANTERIOR_NORM = {"depth": "нормальная", "fluid": "прозрачная"}
NOT_VISIBLE = "не просматривается"
FUNDUS = "Глазное дно"
HIDDEN_BEHIND_FUNDUS = ("Стекловидное тело", "Сосуды", "Сетчатка")

# Objective status: field -> options, the first one is the default (2.9 tab «Объективный осмотр»).
OBJECTIVE: dict[str, list[str]] = {
    "general_state": ["удовлетворительное", "средней тяжести", "тяжёлое"],
    "lymph_nodes": ["не увеличены", "увеличены"],
    "skin_state": ["чистые", "сыпь", "высыпания"],
    "skin_color": ["обычной окраски", "бледные", "гиперемированные"],
    "breathing": ["везикулярное", "жёсткое", "ослабленное"],
    "breathing_side": ["симметричное", "асимметричное"],
    "wheeze": ["нет", "сухие", "влажные"],
    "heart_tones": ["ясные", "приглушённые"],
    "heart_rhythm": ["ритмичные", "аритмичные"],
    "pulse_rhythm": ["ритмичный", "аритмичный"],
    "pulse_quality": ["удовлетворительных свойств", "слабого наполнения"],
    "abdomen_size": ["не вздут", "умеренно вздут"],
    "abdomen_state": ["мягкий", "напряжённый"],
    "abdomen_pain": ["безболезненный", "умеренно болезненный"],
    "liver_position": ["по краю реберной дуги", "ниже реберной дуги"],
    "liver_edge": ["край", "заострённый", "закруглённый"],
    "liver_consistency": ["плотно-эластической консистенции", "плотная"],
    "liver_pain": ["безболезненная", "умеренно болезненная"],
    "stool": ["регулярный", "задержка стула"],
    "stool_form": ["оформленный", "кашицеобразный"],
    "urination": ["свободное", "затруднённое"],
    "urination_pain": ["безболезненное", "болезненное"],
}
ALLERGY = ["не отягощен", "отмечается аллергия на"]
INSURANCE = ["Гражданин ПМР (пенсионер, работает)", "Гражданин ПМР (пенсионер, не работает)",
             "Гражданин ПМР (не работает)", "Гражданин ПМР (работает)", "Гражданства ПМР не имеет (платная основа)"]
DIAG_TYPES = ["клинический", "предварительный"]
COMPLAINT_WORDS = ["на", "боли", "в", "обоих глазах", "правом глазу", "левом глазу", "снижение зрения", ",",
                   "OU", "OD", "OS", "отсутствие зрения", "искажение изображения", "зрительный дискомфорт"]

# Measured, never taken from a template or copied from an earlier exam.
MEASUREMENTS = ("vis_od", "vis_os", "vis_correction_od", "vis_correction_os", "vis_od_corr", "vis_od_result",
                "vis_os_corr", "vis_os_result", "vgd_od", "vgd_os", "bp_sys", "bp_dia", "hr", "pulse")
# Belong to the patient, not to a template.
PERSONAL = ("selected_diagnoses_od", "selected_diagnoses_os", "selected_diagnoses_ou", "custom_diagnosis_od",
            "custom_diagnosis_os", "custom_diagnosis_ou", "diagnosis_free", "selected_comorbid_diagnoses",
            "custom_comorbid_diagnosis", "visit_date", "visit_time")


def local_norm() -> dict:
    local = {}
    for name, options in LOCAL_OPTIONS.items():
        if options is None:
            local[name] = {f"{e}_{k}": v for e in ("od", "os") for k, v in ANTERIOR_NORM.items()}
        else:
            local[name] = {"od_selected": list(NORMS[name]), "od_note": "", "os_selected": list(NORMS[name]), "os_note": ""}
    return local


def normal_exam() -> dict:
    """An exam with everything in the norm and nothing measured — the base every template starts from."""
    data = {
        "schema": "primary_exam_v1", "visit_date": "", "visit_time": "",
        "complaints": "", "disease_anamnesis": "", "tb": "отрицает", "allergy_combo": ALLERGY[0], "allergy_text": "",
        "insurance": INSURANCE[0],
        **{k: v[0] for k, v in OBJECTIVE.items()},
        "hr": "", "pulse": "", "bp_sys": "", "bp_dia": "",
        "local": local_norm(),
        "vis_od": "", "vis_os": "", "vis_correction_od": "пусто", "vis_correction_os": "пусто",
        "vis_od_corr": "", "vis_od_result": "", "vis_os_corr": "", "vis_os_result": "", "vgd_od": "", "vgd_os": "",
        "diag_type": DIAG_TYPES[0], "diagnosis_free": "",
        "selected_diagnoses_od": [], "selected_diagnoses_os": [], "selected_diagnoses_ou": [],
        "custom_diagnosis_od": "", "custom_diagnosis_os": "", "custom_diagnosis_ou": "",
        "selected_comorbid_diagnoses": [], "custom_comorbid_diagnosis": "",
        "selected_examinations": [],
        "treatment": {key: {"selected": [], "note": ""} for key in TREATMENT_LABELS},
    }
    return data


def _empty_cell(name: str) -> dict:
    if name == ANTERIOR:
        return {f"{e}_{k}": "" for e in ("od", "os") for k in ("depth", "fluid")}
    return {"od_selected": [], "od_note": "", "os_selected": [], "os_note": ""}


def complete(data: dict) -> dict:
    """Give partial or older exam data the full shape.

    Local status rows keep the order they were saved in (2.9 printed them in that order), and a
    row missing from the data stays empty — a norm is never filled in that the doctor did not set.
    """
    full = normal_exam()
    if "local" in data:
        saved = data.get("local") or {}
        full["local"] = {name: {**_empty_cell(name), **cell} for name, cell in saved.items()}
        for name in LOCAL_OPTIONS:
            full["local"].setdefault(name, _empty_cell(name))
    for k, v in data.items():
        if k == "local":
            continue
        if k == "treatment":
            for cat, item in (v or {}).items():
                full["treatment"][cat] = {"selected": list(item.get("selected") or []), "note": item.get("note") or ""}
        else:
            full[k] = v
    return full


def apply_fundus_rule(data: dict) -> dict:
    """2.9: when the fundus is «не просматривается», so are the vitreous, vessels and retina of that eye."""
    for eye in ("od", "os"):
        if NOT_VISIBLE in (data["local"].get(FUNDUS, {}).get(f"{eye}_selected") or []):
            for name in HIDDEN_BEHIND_FUNDUS:
                cell = data["local"].setdefault(name, {})
                values = cell.get(f"{eye}_selected") or []
                if NOT_VISIBLE not in values:
                    cell[f"{eye}_selected"] = [NOT_VISIBLE] + [v for v in values if v not in NORMS.get(name, [])]
    return data


def template_part(data: dict) -> dict:
    """What a template keeps: the exam without measurements and without the patient's own diagnoses."""
    part = copy.deepcopy(complete(data))
    for k in MEASUREMENTS + PERSONAL:
        part.pop(k, None)
    return part


def diagnosis_text(d: dict) -> str:
    """«{dx} OD. {dx} OS. {dx} OU» like 2.9, with the free text from admission first."""
    parts = []
    if (d.get("diagnosis_free") or "").strip():
        parts.append(d["diagnosis_free"].strip())
    for eye in ("od", "os", "ou"):
        items = [x for x in d.get(f"selected_diagnoses_{eye}") or [] if x.strip()]
        if (d.get(f"custom_diagnosis_{eye}") or "").strip():
            items.append(d[f"custom_diagnosis_{eye}"].strip())
        if items:
            parts.append(f"{', '.join(items)} {eye.upper()}")
    return ". ".join(parts)


def comorbid_text(d: dict) -> str:
    items = [x for x in d.get("selected_comorbid_diagnoses") or [] if x.strip()]
    if (d.get("custom_comorbid_diagnosis") or "").strip():
        items.append(d["custom_comorbid_diagnosis"].strip())
    return ", ".join(items)


def _cell_text(cell: dict, eye: str, name: str) -> str:
    if name == ANTERIOR:
        depth, fluid = (cell.get(f"{eye}_{k}") or "" for k in ("depth", "fluid"))
        parts = [f"глубина {depth}" if depth and depth != "пусто" else "", f"влага {fluid}" if fluid and fluid != "пусто" else ""]
        return ", ".join(p for p in parts if p)
    out = "; ".join(x for x in cell.get(f"{eye}_selected") or [] if x)
    note = (cell.get(f"{eye}_note") or "").strip()
    if note:
        out = f"{out} (прим.: {note})" if out else f"(прим.: {note})"
    return out


def _e(text) -> str:
    return escape(str(text or "").strip())


def allergy_text(d: dict) -> str:
    if d["allergy_combo"] == ALLERGY[0]:
        return "не отягощен"
    return f"отмечается аллергия на {d['allergy_text'].strip()}" if (d["allergy_text"] or "").strip() else "отмечается аллергия"


def objective_lines(d: dict) -> list[str]:
    """2.9's objective status lines, as plain text."""
    lines = [f"Общее состояние: {d['general_state']}"]
    if d["lymph_nodes"] == "увеличены":
        lines.append("Периферические лимфоузлы: увеличены")
    lines.append(f"Кожные покровы: {d['skin_state']}, {d['skin_color']}")
    lines.append(f"Дыхание: {d['breathing']}, {d['breathing_side']}, хрипы: {d['wheeze']}")
    lines.append(f"Сердечно-сосудистая система: тоны сердца {d['heart_tones']}, ритм {d['heart_rhythm']}, "
                 f"ЧСС {(d['hr'] or '').strip() or '-'} уд/мин, пульс {(d['pulse'] or '').strip() or '-'} уд/мин, "
                 f"{d['pulse_rhythm']}, {d['pulse_quality']}")
    if (d["bp_sys"] or "").strip() or (d["bp_dia"] or "").strip():
        lines.append(f"АД {(d['bp_sys'] or '').strip() or '-'} / {(d['bp_dia'] or '').strip() or '-'} мм рт. ст.")
    lines.append(f"Пищеварительная система: живот {d['abdomen_size']}, {d['abdomen_state']}, {d['abdomen_pain']}, "
                 f"печень {d['liver_position']}, {d['liver_edge']}, {d['liver_consistency']}, {d['liver_pain']}")
    lines.append(f"Стул: {d['stool']}, {d['stool_form']}")
    lines.append(f"Мочеиспускание: {d['urination']}, {d['urination_pain']}")
    return lines


def local_rows(d: dict) -> list[tuple[str, str, str]]:
    """(structure, OD, OS) in the saved order, rows with nothing on either eye left out."""
    rows = [(name, _cell_text(cell, "od", name), _cell_text(cell, "os", name)) for name, cell in d["local"].items()]
    return [r for r in rows if r[1] or r[2]]


def treatment_lines(d: dict) -> list[tuple[str, str]]:
    out = []
    for key, label in TREATMENT_LABELS.items():
        item = d["treatment"].get(key) or {}
        text = "; ".join(x for x in item.get("selected") or [] if x)
        if (item.get("note") or "").strip():
            text = f"{text} (прим.: {item['note'].strip()})" if text else f"(прим.: {item['note'].strip()})"
        if text:
            out.append((label, text))
    return out


_FRAC = """<td style="text-align:center; padding:0 5px; vertical-align:middle;">
<table border="0" cellpadding="2" cellspacing="0">
<tr><td style="text-align:center; border-bottom:1px solid black;">{top}</td></tr>
<tr><td style="text-align:center;">{bottom}</td></tr></table></td>"""
_CELL = '<td style="text-align:center; padding:0 5px; vertical-align:middle;">{}</td>'

_STYLE = """<style>
body{ margin:0; font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; line-height: 1.05; }
.section{ margin:0 0 1mm 0; } .title{ font-weight:700; } div{ margin:0; padding:0; }
table{ margin:0.6mm 0; border-collapse:collapse; font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; }
th, td{ font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; padding: 1px 3px; vertical-align: top; line-height: 1.05; }
b{ line-height:1.05; }
</style>"""


def _diopters(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    return _e(v) if v.endswith(("D", "d", "дптр", "Дптр")) else f"{_e(v)} D"


def render_html(raw: dict, signature: str = "") -> str:
    """The printable text of the exam, built like 2.9's save_primary_exam()."""
    d = complete(raw)
    comp = (d["complaints"] or "").strip()
    out = [_STYLE]
    if comp:
        out.append(f'<div class="section"><span class="title">Жалобы:</span> {_e(comp)}</div>')
    if (d["disease_anamnesis"] or "").strip():
        out.append(f'<div class="section"><span class="title">История настоящего заболевания:</span> {_e(d["disease_anamnesis"])}</div>')

    out.append("<b>Анамнез жизни:</b><br>")
    out.append(f"- Туберкулез, кожвен-заболевания: {_e(d['tb'])}<br>")
    out.append(f"- Аллергологический анамнез: {_e(allergy_text(d))}<br>")
    out.append(f"- Страховой анамнез: {_e(d['insurance'])}")

    out.append('<div class="section"><span class="title">Объективный осмотр:</span></div>')
    out += [f"<div>{_e(ln)}</div>" for ln in objective_lines(d)]
    out.append("<br>")

    out.append("<b>Офтальмологический осмотр:</b><br>")
    vis_od, vis_os = (d["vis_od"] or "").strip(), (d["vis_os"] or "").strip()
    vgd_od, vgd_os = (d["vgd_od"] or "").strip(), (d["vgd_os"] or "").strip()
    if vis_od or vis_os or vgd_od or vgd_os:
        out.append('<table border="0" cellpadding="0" cellspacing="0"><tr>')
        if vis_od or vis_os:
            row = [_CELL.format("<b>Vis</b>"), _FRAC.format(top="OD", bottom="OS"), _CELL.format("="),
                   _FRAC.format(top=_e(vis_od) or "—", bottom=_e(vis_os) or "—")]
            status = {e: "" if d[f"vis_correction_{e}"] in ("пусто", "") else _e(d[f"vis_correction_{e}"]) for e in ("od", "os")}
            corrected = {e: d[f"vis_correction_{e}"] == "с коррекцией" for e in ("od", "os")}
            if status["od"] or status["os"]:
                row.append(_FRAC.format(top=status["od"] or " ", bottom=status["os"] or " ").replace("padding:0 5px", "padding:0 8px", 1))
            if corrected["od"] or corrected["os"]:
                row += [_FRAC.format(top=_diopters(d["vis_od_corr"]) if corrected["od"] else " ",
                                     bottom=_diopters(d["vis_os_corr"]) if corrected["os"] else " "),
                        _CELL.format("="),
                        _FRAC.format(top=_e(d["vis_od_result"]) if corrected["od"] and d["vis_od_result"] else " ",
                                     bottom=_e(d["vis_os_result"]) if corrected["os"] and d["vis_os_result"] else " ")]
            row.append('<td style="padding:0 20px;"></td>')
            out.append("".join(row))
        if vgd_od or vgd_os:
            out.append("".join([_CELL.format("<b>ВГД</b>"), _FRAC.format(top="OD", bottom="OS"), _CELL.format("="),
                                _FRAC.format(top=_e(vgd_od) or "—", bottom=_e(vgd_os) or "—"),
                                '<td style="text-align:left; padding:0 5px; vertical-align:middle;">мм.рт.ст.</td>']))
        out.append("</tr></table><br>")

    rows = local_rows(d)
    if rows:
        out.append('<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">')
        out.append('<tr><th style="text-align:left;">Позиция</th><th style="text-align:left;">OD</th><th style="text-align:left;">OS</th></tr>')
        out += [f"<tr><td><b>{_e(n)}</b></td><td>{_e(od)}</td><td>{_e(os_)}</td></tr>" for n, od, os_ in rows]
        out.append("</table><br>")

    diag = diagnosis_text(d) or "(не указан)"
    full = (f"На основании жалоб {_e(comp)}, истории заболевания, данных биомикроскопии и офтальмоскопии выставлен "
            f"<u>{_e(d['diag_type'])} диагноз</u>: <b>{_e(diag)}</b>")
    if comorbid_text(d):
        full += f"<br><b>Сопутствующий диагноз:</b> {_e(comorbid_text(d))}"
    out.append(f"{full}<br>")

    exams = [x for x in d["selected_examinations"] if x.strip()]
    if exams:
        out.append('<div class="section"><span class="title">План обследования:</span></div>')
        out.append(f"<div>{_e(', '.join(exams))}</div><br>")

    basis = [f"<div><b>{_e(label)}:</b> {_e(text)}</div>" for label, text in treatment_lines(d)]
    if basis:
        out.append('<div class="section"><span class="title">Обоснование лечения:</span></div>')
        out += basis
        out.append("<br>")

    who = f"{_e(signature)} " if signature.strip() else "Подпись "
    out.append(f'<div style="margin-top:6mm; text-align:right;">{who}__________________</div>')
    return "".join(out)


def admission_prefill(case: dict) -> dict:
    """Diagnoses known from admission go into a new exam (the doctor refines them)."""
    return {
        "diagnosis_free": (case.get("dx_clinical") or case.get("dx_admission") or "").strip(),
        "custom_comorbid_diagnosis": (case.get("dx_comorbid") or "").strip(),
    }


def matches(template_keywords: str, diagnosis: str) -> bool:
    words = [w for w in re.split(r"[,\s]+", template_keywords.casefold()) if len(w) >= 4]
    dx = diagnosis.casefold()
    return any(w[:-1] in dx for w in words)   # «катаракта» matches «катаракты», «глаукома» — «глаукомы»


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)
