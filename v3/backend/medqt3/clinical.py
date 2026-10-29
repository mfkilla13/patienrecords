"""Turn stored records into view data for the case screen.

Vision is normalized the way 2.9.x printed it: Vis as an OD/OS fraction,
then a status column (n.k., счёт пальцев, ...), then "correction = result"
for eyes examined «с коррекцией», then ВГД as an OD/OS fraction.
"""

from __future__ import annotations

import json

KIND_LABELS = {
    "primary_exam": "Первичный осмотр",
    "diary": "Дневник",
    "operation_protocol": "Протокол операции",
    "discharge_summary": "Выписной эпикриз",
    "plan": "План обследования и лечения",
    "passport": "Паспортная часть",
    "other": "Запись",
}

TREATMENT_LABELS = {
    "angio_retino": "Ангиоретинопротектор",
    "metabolism": "Для улучшения обмена веществ",
    "desensitization": "Десенсибилизанты",
    "antibiotics": "Антибиотики",
    "angioprotectors": "Ангиопротекторы",
    "myotics": "Миотики",
    "biostimulators": "Биостимуляторы",
    "vasodilators": "Сосудорасширяющие",
    "analgesics": "Анальгетики",
    "antiaggregants": "Антиагреганты",
    "antifungal": "Противогрибковые",
    "mydriatics": "Мидриатики",
    "k_sparing": "К-сберегающий",
    "anesthetics": "Анестетики",
    "hypoglycemic": "Сахоропонижающие",
    "hypotensive": "Гипотензивное",
    "diuretic": "Мочегонное",
    "antithrombotic": "Антитромбической цели",
}

WITH_CORRECTION = "с коррекцией"


def _s(value) -> str:
    return str(value).strip() if value is not None else ""


def _status(text: str) -> str:
    if text in ("", "пусто", WITH_CORRECTION):
        return ""
    if text == "n.k. (не коррег.)":
        return "n.k."
    return text


def _diopters(text: str) -> str:
    text = _s(text)
    if not text or text.lower().endswith(("d", "дптр")):
        return text
    return f"{text} D"


def vision(d: dict) -> dict | None:
    """Vis / status / correction / ВГД for OD and OS, or None when nothing was measured."""
    eyes = {}
    for eye in ("od", "os"):
        corr_mode = _s(d.get(f"vis_correction_{eye}"))
        corrected = corr_mode == WITH_CORRECTION
        eyes[eye] = {
            "vis": _s(d.get(f"vis_{eye}")),
            "status": _status(corr_mode),
            "corr": _diopters(d.get(f"vis_{eye}_corr")) if corrected else "",
            "result": _s(d.get(f"vis_{eye}_result")) if corrected else "",
            "iop": _s(d.get(f"vgd_{eye}")),
        }
    if not any(v for e in eyes.values() for v in e.values()):
        return None
    return eyes


def _treatment_lines(treatment: dict | None) -> list[str]:
    lines = []
    for key, label in TREATMENT_LABELS.items():
        item = (treatment or {}).get(key) or {}
        values = [_s(v) for v in item.get("selected") or [] if _s(v)]
        if _s(item.get("note")):
            values.append(f"прим.: {_s(item['note'])}")
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    return lines


def _section(sections: list, label: str, text: str) -> None:
    if _s(text):
        sections.append({"label": label, "text": _s(text)})


def _diary(d: dict) -> dict:
    sections: list = []
    vitals = []
    if _s(d.get("bp")):
        vitals.append(f"АД {_s(d['bp'])} мм рт. ст.")
    if _s(d.get("hr")):
        vitals.append(f"ЧСС {_s(d['hr'])} уд/мин")
    if _s(d.get("pulse")):
        vitals.append(f"пульс {_s(d['pulse'])} уд/мин")
    _section(sections, "", " · ".join(vitals))
    _section(sections, "Общее состояние", d.get("general_state"))
    _section(sections, "Жалобы", d.get("complaints"))
    for eye in ("od", "os", "ou"):
        _section(sections, eye.upper(), d.get(f"{eye}_text"))
    treatment = " ".join(x for x in [_s(d.get("treatment"))] + _treatment_lines(d.get("basis")) if x)
    _section(sections, "Лечение", treatment)
    _section(sections, "Для выписки", d.get("discharge_note"))
    return {"sections": sections}


def _primary_exam(d: dict) -> dict:
    sections: list = []
    _section(sections, "Жалобы", d.get("complaints"))
    _section(sections, "История настоящего заболевания", d.get("disease_anamnesis"))
    bp = "/".join(x for x in [_s(d.get("bp_sys")), _s(d.get("bp_dia"))] if x)
    general = ", ".join(x for x in [
        _s(d.get("general_state")) and f"общее состояние {_s(d.get('general_state'))}",
        bp and f"АД {bp} мм рт. ст.",
        _s(d.get("hr")) and f"ЧСС {_s(d.get('hr'))} уд/мин",
    ] if x)
    _section(sections, "Объективно", general)

    local = []
    for name, cell in (d.get("local") or {}).items():
        row = {"name": name}
        for eye in ("od", "os"):
            parts = [_s(x) for x in cell.get(f"{eye}_selected") or [] if _s(x)]
            for extra in ("depth", "fluid"):
                if _s(cell.get(f"{eye}_{extra}")) not in ("", "пусто"):
                    parts.append(("глубина " if extra == "depth" else "влага ") + _s(cell[f"{eye}_{extra}"]))
            text = "; ".join(parts)
            if _s(cell.get(f"{eye}_note")):
                text = f"{text} (прим.: {_s(cell[f'{eye}_note'])})" if text else _s(cell[f"{eye}_note"])
            row[eye] = text
        if row["od"] or row["os"]:
            local.append(row)

    dx = []
    for eye in ("od", "os", "ou"):
        items = [_s(x) for x in d.get(f"selected_diagnoses_{eye}") or [] if _s(x)]
        if _s(d.get(f"custom_diagnosis_{eye}")):
            items.append(_s(d[f"custom_diagnosis_{eye}"]))
        if items:
            dx.append(f"{', '.join(items)} {eye.upper()}")
    dx_label = f"Диагноз ({_s(d.get('diag_type'))})" if _s(d.get("diag_type")) else "Диагноз"
    _section(sections, dx_label, ". ".join(dx))
    comorbid = [_s(x) for x in d.get("selected_comorbid_diagnoses") or [] if _s(x)]
    if _s(d.get("custom_comorbid_diagnosis")):
        comorbid.append(_s(d["custom_comorbid_diagnosis"]))
    _section(sections, "Сопутствующий", ", ".join(comorbid))
    _section(sections, "План обследования", ", ".join(_s(x) for x in d.get("selected_examinations") or [] if _s(x)))
    _section(sections, "Обоснование лечения", "\n".join(_treatment_lines(d.get("treatment"))))
    return {"sections": sections, "local": local}


def _operation(d: dict) -> dict:
    sections: list = []
    _section(sections, "Операция", d.get("operation_name"))
    _section(sections, "", d.get("description"))
    return {"sections": sections, "title": _s(d.get("operation_name"))}


def _discharge(d: dict) -> dict:
    sections: list = []
    _section(sections, "Эпикриз", d.get("epicrisis"))
    _section(sections, "Местный статус при выписке", d.get("local_status_text"))
    _section(sections, "Лечение", d.get("treatment_summary"))
    _section(sections, "Рекомендации", d.get("recommendations"))
    return {"sections": sections}


BUILDERS = {"diary": _diary, "primary_exam": _primary_exam, "operation_protocol": _operation,
            "discharge_summary": _discharge}


def record_view(row) -> dict:
    data = json.loads(row["data_json"]) if row["data_json"] else None
    view = {
        "id": row["id"],
        "kind": row["kind"],
        "kindLabel": KIND_LABELS.get(row["kind"], "Запись"),
        "recordedAt": row["recorded_at"][:16],
        "printedAt": row["printed_at"],
        "vision": None,
        "sections": [],
        "local": [],
        "title": "",
        "hasLegacyHtml": False,
        "editable": row["kind"] in ("diary", "primary_exam") and data is not None and not row["printed_at"],
    }
    builder = BUILDERS.get(row["kind"])
    if data is not None and builder:
        view.update(builder(data))
        view["vision"] = vision(data)
    else:
        view["hasLegacyHtml"] = bool(row["html_legacy"])
        if row["kind"] == "other" and row["html_legacy"]:
            view["kindLabel"] = row["html_legacy"].split(":", 1)[0][:60] or "Запись"
    return view
