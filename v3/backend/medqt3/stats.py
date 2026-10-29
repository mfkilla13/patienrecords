"""Statistics: 2.9's five charts on one page — admissions, discharges, average stay, diagnoses, outcomes.

Admissions count by the admission date; discharges, the average stay and the outcomes by the
discharge date. Diagnoses are grouped like the archive filter (катаракта, глаукома, ...), for the
cases admitted in the period. The grouping of the time axis follows the length of the period:
days up to two months, months up to three years, years beyond.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .archive import NO_DX, dx_groups
from .discharge import stay_days
from .importer import to_date

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


class StatsError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _grouping(start: date, end: date) -> str:
    days = (end - start).days + 1
    return "day" if days <= 62 else "month" if days <= 3 * 366 else "year"


def _key(d: str, group: str) -> str:
    return d[:10] if group == "day" else d[:7] if group == "month" else d[:4]


def _buckets(start: date, end: date, group: str) -> list[tuple[str, str]]:
    """Every period in the range, empty ones too, so the axis is not squeezed: (key, label)."""
    out = []
    if group == "day":
        d = start
        while d <= end:
            out.append((d.isoformat(), f"{d.day:02d}.{d.month:02d}"))
            d += timedelta(days=1)
    elif group == "month":
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            out.append((f"{y:04d}-{m:02d}", f"{MONTHS[m - 1]} {str(y)[2:]}"))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    else:
        out = [(str(y), str(y)) for y in range(start.year, end.year + 1)]
    return out


def compute(conn: sqlite3.Connection, date_from: str | None, date_to: str | None, today: date | None = None) -> dict:
    today = today or date.today()
    rows = conn.execute(
        "SELECT admitted_at, discharged_at, status, outcome, dx_final, dx_clinical, dx_admission"
        " FROM cases WHERE deleted_at IS NULL").fetchall()
    first = min((to_date(r["admitted_at"]) for r in rows if to_date(r["admitted_at"])), default=today.isoformat())
    start = date.fromisoformat(to_date(date_from) or first)
    end = date.fromisoformat(to_date(date_to) or today.isoformat())
    if start > end:
        raise StatsError(422, "Начало периода позже конца")
    group = _grouping(start, end)
    lo, hi = start.isoformat(), end.isoformat()

    def inside(iso: str | None) -> str | None:
        d = to_date(iso)
        return d if d and lo <= d <= hi else None

    admitted = {k: 0 for k, _ in _buckets(start, end, group)}
    discharged = dict(admitted)
    stays: dict[str, list[int]] = {k: [] for k in admitted}
    diagnoses: dict[str, int] = {}
    outcomes: dict[str, int] = {}
    all_stays: list[int] = []
    for r in rows:
        a = inside(r["admitted_at"])
        if a:
            admitted[_key(a, group)] += 1
            for g in dx_groups(r["dx_final"] or r["dx_clinical"] or r["dx_admission"] or ""):
                diagnoses[g] = diagnoses.get(g, 0) + 1
        d = inside(r["discharged_at"]) if r["status"] != "active" else None
        if d:
            discharged[_key(d, group)] += 1
            outcome = (r["outcome"] or "").strip().lower() or "не указан"
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            days = stay_days(r["admitted_at"], r["discharged_at"])
            if days is not None and days > 0:
                stays[_key(d, group)].append(days)
                all_stays.append(days)

    labels = dict(_buckets(start, end, group))

    def series(values: dict) -> list[dict]:
        return [{"key": k, "label": labels[k], "value": v} for k, v in values.items()]

    def ranked(counts: dict, last: tuple[str, ...]) -> list[dict]:
        # Largest first; «Другое» / «Не указан» always at the end.
        items = sorted(((k, v) for k, v in counts.items() if k not in last), key=lambda x: (-x[1], x[0]))
        items += [(k, counts[k]) for k in last if k in counts]
        return [{"label": k[:1].upper() + k[1:], "value": v} for k, v in items]

    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {
        "from": lo, "to": hi, "group": group,
        "totals": {
            "admitted": sum(admitted.values()),
            "discharged": sum(discharged.values()),
            "avgStay": avg(all_stays),
            "inDepartment": sum(1 for r in rows if r["status"] in ("active", "discharged")),
        },
        "admissions": series(admitted),
        "discharges": series(discharged),
        "avgStay": [{"key": k, "label": labels[k], "value": avg(v), "n": len(v)} for k, v in stays.items()],
        "diagnoses": ranked(diagnoses, ("Другое", NO_DX)),
        "outcomes": ranked(outcomes, ("не указан",)),
        "firstDate": first,
    }
