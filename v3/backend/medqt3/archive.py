"""Archive (архив): closed case histories — search, filters by period, diagnosis group and outcome, export.

Filtering is done in Python, not SQL: SQLite's lower() does not fold Cyrillic, and the
archive is small (tens of cases a month), so reading it whole is cheap.
Diagnoses are free text with typos («ктаракта», «глауком»), so groups match word stems.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import date

from .discharge import stay_days
from .importer import to_date

# Diagnosis groups for the filter: label -> stems found in the diagnosis text.
DX_GROUPS: dict[str, tuple[str, ...]] = {
    "Катаракта": ("катаракт", "ктаракт", "катарак"),
    "Глаукома": ("глауком",),
    "Артифакия": ("артифаки", "артефаки"),
    "Миопия": ("миопи", "близорук"),
    "Макулодистрофия": ("макулодистр", "макулярн", "дегенерац"),
    "Ретинопатия": ("ретинопат",),
    "Нейрооптикопатия": ("нейрооптикопат", "атрофия зрительного"),
    "Гемофтальм": ("гемофтальм",),
    "Роговица": ("кератит", "кератопат", "лейком", "эрозия роговиц", "язва роговиц"),
    "Увеит, иридоциклит": ("увеит", "иридоциклит"),
    "Слёзные пути": ("дакриоцист", "слезн", "слёзн"),
    "Веки": ("ячмен", "ксантелазм", "ксантилазм", "халязион", "халазион", "блефарит", "выворот век", "заворот век"),
    "Птеригиум": ("птеригиум",),
    "Ожог, травма": ("ожог", "травм", "инородн"),
}
OTHER = "Другое"
NO_DX = "Не указан"
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
          "Ноябрь", "Декабрь"]
_EYE = re.compile(r"\b(OD|OS|OU)\b")


def _fold(text: str) -> str:
    return (text or "").lower().replace("ё", "е")


def dx_groups(dx: str) -> list[str]:
    t = _fold(dx)
    if not t.strip() or t.strip() in ("(не указан)", "не указан"):
        return [NO_DX]
    found = [g for g, stems in DX_GROUPS.items() if any(s in t for s in stems)]
    return found or [OTHER]


def _row(r: sqlite3.Row) -> dict:
    dx = r["dx_final"] or r["dx_clinical"] or r["dx_admission"] or ""
    eyes = list(dict.fromkeys(_EYE.findall(dx)))
    return {
        "caseId": r["id"], "number": r["number"],
        "patient": " ".join(x for x in (r["surname"], r["name"], r["patronymic"]) if x),
        "dob": r["dob"], "dx": dx, "eye": "OU" if len(eyes) > 1 else (eyes[0] if eyes else ""),
        "groups": dx_groups(dx), "admittedAt": r["admitted_at"], "dischargedAt": r["discharged_at"],
        "days": stay_days(r["admitted_at"], r["discharged_at"]), "outcome": r["outcome"] or "",
    }


def _all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT c.*, p.surname, p.name, p.patronymic, p.dob FROM cases c JOIN patients p ON p.id = c.patient_id"
        " WHERE c.status = 'archived' AND c.deleted_at IS NULL"
        " ORDER BY COALESCE(c.discharged_at, c.archived_at, '') DESC, c.number DESC").fetchall()
    return [_row(r) for r in rows]


def _matches(row: dict, q: str) -> bool:
    """Surname/name, history number or date of birth («14.05.1956», «1956»); every word must match."""
    hay = " ".join([_fold(row["patient"]), _fold(row["number"]), row["dob"] or "",
                    _fold(row["dx"])])
    for word in _fold(q).split():
        iso = to_date(word)
        if iso and iso == row["dob"]:
            continue
        if word not in hay:
            return False
    return True


def _in_period(row: dict, period: str) -> bool:
    if not period or period == "all":
        return True
    return (row["dischargedAt"] or "").startswith(period)   # "2026" or "2026-04"


def search(conn: sqlite3.Connection, q: str = "", period: str = "all", dx: str = "", outcome: str = "",
           page: int = 1, size: int = 12) -> dict:
    rows = _all(conn)
    found = [r for r in rows if _in_period(r, period) and (not dx or dx in r["groups"])
             and (not outcome or r["outcome"] == outcome) and (not q.strip() or _matches(r, q))]
    pages = max(1, -(-len(found) // size))
    page = min(max(1, page), pages)

    # Filter options come from the whole archive, so a choice never leads to an empty list by itself.
    months = sorted({(r["dischargedAt"] or "")[:7] for r in rows if r["dischargedAt"]}, reverse=True)
    years = sorted({m[:4] for m in months}, reverse=True)
    periods = [{"value": "all", "label": "За всё время"}]
    for y in years:
        periods.append({"value": y, "label": f"Весь {y} год"})
        periods += [{"value": m, "label": f"{MONTHS[int(m[5:7]) - 1]} {y}"} for m in months if m.startswith(y)]
    groups: dict[str, int] = {}
    for r in rows:
        for g in r["groups"]:
            groups[g] = groups.get(g, 0) + 1
    outcomes: dict[str, int] = {}
    for r in rows:
        if r["outcome"]:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1

    return {
        "total": len(rows), "found": len(found), "page": page, "pages": pages, "size": size,
        "rows": found[(page - 1) * size: page * size],
        "periods": periods,
        "dxGroups": [{"value": g, "count": n} for g, n in sorted(groups.items(), key=lambda kv: (kv[0] in (OTHER, NO_DX), kv[0] == NO_DX, -kv[1]))],
        "outcomes": [{"value": o, "count": n} for o, n in sorted(outcomes.items(), key=lambda kv: -kv[1])],
    }


def _ru(iso: str | None) -> str:
    d = to_date(iso)
    return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if d else ""


def export_csv(conn: sqlite3.Connection, q: str = "", period: str = "all", dx: str = "", outcome: str = "") -> bytes:
    """The filtered list for Excel: «;» separated with a BOM, which Russian Excel opens directly."""
    res = search(conn, q, period, dx, outcome, page=1, size=10 ** 6)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\r\n")
    w.writerow(["№ истории", "Пациент", "Дата рождения", "Диагноз", "Глаз", "Поступление", "Выписка", "Койко-дней", "Исход"])
    for r in res["rows"]:
        w.writerow([r["number"], r["patient"], _ru(r["dob"]), r["dx"], r["eye"], _ru(r["admittedAt"]),
                    _ru(r["dischargedAt"]), r["days"] if r["days"] is not None else "", r["outcome"]])
    return ("﻿" + out.getvalue()).encode("utf-8")


def export_name(period: str) -> str:
    return f"medqt-arhiv-{period if period and period != 'all' else date.today().isoformat()}.csv"
