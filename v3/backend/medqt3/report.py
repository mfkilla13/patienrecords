"""The department report (отчёт отделения) as the department hands it in: the main indicators,
«Структура пролеченных больных» by nosology, operations, outcomes and how patients came.

Everything is counted from the cases: admissions by the admission date; discharges, bed-days,
the structure and outcomes by the discharge date; operations by the protocol date. Bed-days use
the same count as the выписка (discharge.stay_days) — one place to change if the department's
statistician counts them differently.

The nosology of a case is chosen at discharge («группа для отчёта»); cases without one (all
cases moved from 2.9) get a suggestion from the diagnosis, and the report lists them for a check.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, timedelta

from . import db as store
from . import dicts, settings
from .discharge import stay_days
from .importer import to_date

# The rows of «Структура пролеченных больных», in the order of the department's reports.
GROUPS = ["Глаукома", "Катаракта", "Кератиты", "Увеиты", "Диабетические ретинопатии",
          "Травмы глаз с повреждением век и конъюнктивы", "Проникающие ранения",
          "Заболевания век и слезного аппарата", "Заболевания стекловидного тела", "Заболевания зрительного нерва",
          "Заболевания сетчатки", "Аномалии рефракции", "Высокая осложнённая близорукость", "Врождённые аномалии",
          "Эндофтальмит", "Другие заболевания глаза"]
OTHER_GROUP = "Другие заболевания глаза"

# Suggestion from the diagnosis: the first rule that matches wins, so the more specific and the more
# likely reason for the stay go first (a glaucoma attack beats an incidental cataract in the same text).
_RULES = [
    ("Проникающие ранения", ("проникающ",)),
    ("Эндофтальмит", ("эндофтальмит",)),
    ("Травмы глаз с повреждением век и конъюнктивы", ("травм", "ожог", "ранени", "разрыв", "инородн", "контузи")),
    ("Глаукома", ("глауком", "глаукм", "галуком")),
    ("Увеиты", ("увеит", "увейт", "иридоциклит", "ирит")),
    ("Кератиты", ("кератит", "язва роговиц", "кератопат", "эрозия роговиц")),
    ("Диабетические ретинопатии", ("диабетическ",)),
    ("Заболевания зрительного нерва", ("нейрооптикопат", "зрительного нерва", "зрительных нервов", "неврит", "атрофия зн")),
    ("Заболевания стекловидного тела", ("гемофтальм", "стекловидн")),
    ("Высокая осложнённая близорукость", ("осложненная близорук", "осложнённая близорук", "близорукость высок")),
    ("Заболевания сетчатки", ("сетчатк", "макулодистро", "макулярн", "ретинопат", "окклюзи", "тромбоз")),
    ("Заболевания век и слезного аппарата", ("век", "веко", "халязион", "холязион", "ячмен", "дакриоцист", "слезн",
                                             "атерома", "ксантелазм", "ксантилазм", "блефарит", "заворот", "выворот")),
    ("Врождённые аномалии", ("врожденн", "врождённ", "колобом", "микрофтальм")),
    ("Катаракта", ("катаракт", "ктаракт")),
    ("Аномалии рефракции", ("миопи", "близорук", "гиперметроп", "астигмат", "дальнозор")),
]

CHANNELS = {
    "экстренно из приёмного отделения": "emergency",
    "доставлен СМП": "emergency",
    "самообращение": "emergency",
    "переведён из АРО": "emergency",
    "переведён из другого отделения": "emergency",
    "направлен профильным специалистом КП": "planned",
    "направлен смежным специалистом другого ЛПУ": "planned",
}
RESIDENCE = ["", "иногородний", "иностранный гражданин"]

OP_TYPES = ["Экстракция катаракты", "Антиглаукоматозные операции", "ПХО травм век, конъюнктивы", "Проникающие ранения",
            "Пластические операции", "Операции на веках", "Операции на слёзных органах", "Энуклеации",
            "Удаление инородных тел", "Прочие операции"]
_OP_RULES = [
    ("Экстракция катаракты", ("катаракт", "факоэмульс", "экстракци")),
    ("Антиглаукоматозные операции", ("глауком", "трабекул", "синустрабекул", "иридэктоми")),
    ("Удаление инородных тел", ("инородн",)),
    ("Проникающие ранения", ("проникающ",)),
    ("ПХО травм век, конъюнктивы", ("пхо", "хирургическая обработка")),
    ("Энуклеации", ("энуклеац", "энукуляц")),
    ("Операции на слёзных органах", ("слезн", "слёзн", "дакрио")),
    ("Пластические операции", ("пластик", "пластич", "птеригиум")),
    ("Операции на веках", ("век", "халязион", "холязион", "ячмен", "абсцесс", "атерома", "ксантелазм")),
]
URGENCY = {"срочно": "urgent", "планово": "planned"}

# Outcomes as written by 2.9 and by the выписка form -> the report's wording.
_OUTCOMES = [("С выздоровлением", ("выздоровл",)), ("С улучшением", ("улучшен",)), ("Без перемен", ("без перемен",)),
             ("С ухудшением", ("ухудшен",)), ("Переведён", ("перевод", "переведен", "переведён")),
             ("Самовольно покинул", ("самовольн",)), ("Умер", ("смерть", "умер", "летальн"))]


def _fold(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def suggest_group(dx: str) -> str:
    t = _fold(dx)
    if not t.strip():
        return OTHER_GROUP
    for group, stems in _RULES:
        if any(_fold(s) in t for s in stems):
            # «век» must be a word start, not a part of «человек» or «навек».
            if group == "Заболевания век и слезного аппарата" and not re.search(
                    r"(^|[^а-я])(век|веко|халязион|холязион|ячмен|дакриоцист|слезн|атерома|ксант|блефарит|заворот|выворот)", t):
                continue
            return group
    return OTHER_GROUP


def suggest_op_type(name: str) -> str:
    t = _fold(name)
    for op, stems in _OP_RULES:
        if any(_fold(s) in t for s in stems):
            return op
    return "Прочие операции"


def outcome_label(outcome: str) -> str:
    t = _fold(outcome)
    for label, stems in _OUTCOMES:
        if any(_fold(s) in t for s in stems):
            return label
    return "С улучшением" if not t.strip() else outcome.strip().capitalize()


def _age(dob: str | None, on: str | None) -> int | None:
    d, at = to_date(dob), to_date(on)
    if not d or not at or d > at:
        return None
    y, m, dd = (int(x) for x in d.split("-"))
    a = date.fromisoformat(at)
    return a.year - y - ((a.month, a.day) < (m, dd))


def _num(conn: sqlite3.Connection, key: str) -> int:
    v = settings.get(conn).get(key) or ""
    return int(v) if v.isdigit() else 0


def _one(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _period(conn: sqlite3.Connection, lo: str, hi: str, beds: int, plan_year: int, villages: set[str]) -> dict:
    cases = conn.execute(
        "SELECT c.id, c.number, c.admitted_at, c.discharged_at, c.status, c.outcome, c.report_group,"
        " c.admission_channel, c.dx_final, c.dx_clinical, c.dx_admission,"
        " p.surname, p.name, p.patronymic, p.dob, p.city, p.residence"
        " FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.deleted_at IS NULL").fetchall()

    def inside(iso: str | None) -> bool:
        d = to_date(iso)
        return bool(d) and lo <= d <= hi

    admitted = [c for c in cases if inside(c["admitted_at"])]
    left = [c for c in cases if c["status"] != "active" and inside(c["discharged_at"])]
    died = [c for c in left if outcome_label(c["outcome"]) == "Умер"]
    treated = left
    stay = {c["id"]: stay_days(c["admitted_at"], c["discharged_at"]) or 0 for c in cases}
    bed_days = sum(stay[c["id"]] for c in treated)
    days = (date.fromisoformat(hi) - date.fromisoformat(lo)).days + 1
    work = bed_days / beds if beds else None
    turnover = len(treated) / beds if beds else None
    idle = (days - work) / turnover if work is not None and turnover else None
    plan = plan_year * days / 365 if plan_year else 0

    def rural(c) -> bool:
        return _fold(c["city"]).strip() in villages

    main = {
        "beds": beds,
        "treated": len(treated),
        "admitted": len(admitted),
        "discharged": len(left) - len(died),
        "died": len(died),
        "bedDays": bed_days,
        "avgStay": _one(bed_days / len(treated)) if treated else None,
        "bedWork": _one(work),
        "turnover": _one(turnover),
        "bedIdle": _one(idle),
        "planPercent": _one(bed_days / plan * 100) if plan else None,
        "rural": sum(1 for c in treated if rural(c)),
        "ruralPercent": _one(sum(1 for c in treated if rural(c)) / len(treated) * 100) if treated else None,
        "nonresident": sum(1 for c in treated if c["residence"] == "иногородний"),
        "foreign": sum(1 for c in treated if c["residence"] == "иностранный гражданин"),
        "children": sum(1 for c in treated if (a := _age(c["dob"], c["admitted_at"])) is not None and a < 15),
        "teens": sum(1 for c in treated if (a := _age(c["dob"], c["admitted_at"])) is not None and 15 <= a <= 17),
    }

    channels = {k: 0 for k in CHANNELS}
    for c in admitted:
        if c["admission_channel"] in channels:
            channels[c["admission_channel"]] += 1
    main["emergency"] = sum(v for k, v in channels.items() if CHANNELS[k] == "emergency")
    main["planned"] = sum(v for k, v in channels.items() if CHANNELS[k] == "planned")
    main["channelUnknown"] = sum(1 for c in admitted if c["admission_channel"] not in CHANNELS)

    outcomes: dict[str, int] = {}
    for c in left:
        label = outcome_label(c["outcome"])
        outcomes[label] = outcomes.get(label, 0) + 1

    rows = {g: {"count": 0, "bedDays": 0} for g in GROUPS}
    auto = []
    for c in treated:
        dx = c["dx_final"] or c["dx_clinical"] or c["dx_admission"] or ""
        group = c["report_group"] if c["report_group"] in rows else suggest_group(dx)
        if c["report_group"] not in rows:
            auto.append({"caseId": c["id"], "number": c["number"], "dx": dx, "group": group,
                         "patient": " ".join(x for x in (c["surname"], c["name"], c["patronymic"]) if x)})
        rows[group]["count"] += 1
        rows[group]["bedDays"] += stay[c["id"]]
    structure = [{"label": g, "count": r["count"], "share": _one(r["count"] / len(treated) * 100) if treated else None,
                  "bedDays": r["bedDays"], "avgStay": _one(r["bedDays"] / r["count"]) if r["count"] else None}
                 for g, r in rows.items()]

    case_by_id = {c["id"]: c for c in cases}
    protocols = conn.execute(
        "SELECT r.case_id, r.recorded_at, r.data_json FROM records r JOIN cases c ON c.id = r.case_id"
        " WHERE r.kind = 'operation_protocol' AND r.deleted_at IS NULL AND c.deleted_at IS NULL").fetchall()
    ops = {t: {"count": 0, "bedDays": 0} for t in OP_TYPES}
    operated = {"urgent": set(), "planned": set()}
    op_count = {"urgent": 0, "planned": 0, "unknown": 0}
    complications = {"urgent": 0, "planned": 0}
    for r in protocols:
        if not inside(r["recorded_at"]):
            continue
        d = json.loads(r["data_json"]) if r["data_json"] else {}
        t = d.get("op_type") if d.get("op_type") in ops else suggest_op_type(d.get("operation_name", ""))
        ops[t]["count"] += 1
        ops[t]["bedDays"] += stay.get(r["case_id"], 0) if case_by_id[r["case_id"]]["status"] != "active" else 0
        u = URGENCY.get(d.get("urgency", ""), "unknown")
        op_count[u] += 1
        if u != "unknown":
            operated[u].add(r["case_id"])
            complications[u] += 1 if d.get("complication") else 0
    total_ops = sum(o["count"] for o in ops.values())
    operations = [{"label": t, "count": o["count"], "share": _one(o["count"] / total_ops * 100) if total_ops else None,
                   "bedDays": o["bedDays"], "avgStay": _one(o["bedDays"] / o["count"]) if o["count"] else None}
                  for t, o in ops.items()]
    surgery = {"operations": total_ops, "urgent": op_count["urgent"], "planned": op_count["planned"],
               "urgencyUnknown": op_count["unknown"],
               "operatedUrgent": len(operated["urgent"]), "operatedPlanned": len(operated["planned"]),
               "complicationsUrgent": complications["urgent"], "complicationsPlanned": complications["planned"]}

    return {"from": lo, "to": hi, "hasData": bool(admitted or left), "main": main,
            "channels": [{"label": k, "kind": v, "count": channels[k]} for k, v in CHANNELS.items()],
            "outcomes": [{"label": k, "count": v} for k, v in sorted(outcomes.items(), key=lambda x: -x[1])],
            "structure": structure, "operations": operations, "surgery": surgery,
            "autoGroups": sorted(auto, key=lambda x: x["number"])}


def _year_back(iso: str) -> str:
    d = date.fromisoformat(iso)
    try:
        return d.replace(year=d.year - 1).isoformat()
    except ValueError:                       # 29 February
        return (d.replace(day=28, year=d.year - 1)).isoformat()


def compute(conn: sqlite3.Connection, date_from: str, date_to: str) -> dict:
    lo, hi = to_date(date_from), to_date(date_to)
    if not lo or not hi:
        raise ValueError("Укажите период отчёта")
    if lo > hi:
        raise ValueError("Начало периода позже конца")
    beds, plan = _num(conn, "beds"), _num(conn, "bed_days_plan")
    villages = {_fold(v).strip() for v in dicts.get(conn, "addresses").get("villages", [])}
    current = _period(conn, lo, hi, beds, plan, villages)
    previous = _period(conn, _year_back(lo), _year_back(hi), beds, plan, villages)
    previous.pop("autoGroups")
    return {"current": current, "previous": previous, "groups": GROUPS, "channels": list(CHANNELS),
            "opTypes": OP_TYPES, "residence": RESIDENCE, "villages": sorted(dicts.get(conn, "addresses").get("villages", []))}


def set_group(conn: sqlite3.Connection, case_id: str, group: str) -> None:
    if group and group not in GROUPS:
        raise ValueError("Нет такой группы")
    with conn:
        n = conn.execute("UPDATE cases SET report_group = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                         (group, store.now_iso(), case_id)).rowcount
    if not n:
        raise LookupError("История не найдена")


def periods(today: date | None = None) -> list[dict]:
    """Ready-made periods for the report page: last year, this year's halves and quarters, last month."""
    t = today or date.today()
    y = t.year
    first_this_month = t.replace(day=1)
    last_month_end = first_this_month - timedelta(days=1)
    out = [
        {"key": f"{y - 1}", "label": f"{y - 1} год", "from": f"{y - 1}-01-01", "to": f"{y - 1}-12-31"},
        {"key": f"{y}-h1", "label": f"1 полугодие {y}", "from": f"{y}-01-01", "to": f"{y}-06-30"},
        {"key": f"{y}-h2", "label": f"2 полугодие {y}", "from": f"{y}-07-01", "to": f"{y}-12-31"},
        {"key": f"{y}", "label": f"{y} год", "from": f"{y}-01-01", "to": f"{y}-12-31"},
    ]
    for q in range(1, 5):
        start = date(y, 3 * q - 2, 1)
        end = (date(y, 3 * q + 1, 1) if q < 4 else date(y + 1, 1, 1)) - timedelta(days=1)
        if start <= t:
            out.append({"key": f"{y}-q{q}", "label": f"{q} квартал {y}", "from": start.isoformat(), "to": end.isoformat()})
    out.append({"key": "last-month", "label": "Прошлый месяц", "from": last_month_end.replace(day=1).isoformat(),
                "to": last_month_end.isoformat()})
    return out
