"""User settings, kept in the meta table so they travel with the database.

2.9 had the doctor's name and the institution hard-coded in its print code; here
they are settings, with 2.9's institution header as the default.
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel, Field, field_validator

DEFAULTS = {
    "doctor_signature": "",
    "org_header": "Министерство здравоохранения\nПриднестровской Молдавской Республики\nГУ БГЦБ",
    "department": "Офтальмологическое отделение",
    "default_printer": "",
    "beds": "20",                 # for the department report: bed turnover, days of bed work
    "bed_days_plan": "",          # planned bed-days per year (% of the plan); empty — not shown
    "theme": "auto",              # auto (as in Windows) | light | dark
}


class SettingsIn(BaseModel):
    doctor_signature: str = Field("", max_length=80)
    org_header: str = Field("", max_length=400)
    department: str = Field("", max_length=120)
    default_printer: str = Field("", max_length=200)
    beds: str = Field("20", max_length=4, pattern=r"^\d{0,4}$")
    bed_days_plan: str = Field("", max_length=6, pattern=r"^\d{0,6}$")
    theme: str = Field("auto", pattern=r"^(auto|light|dark)$")

    @field_validator("*")
    @classmethod
    def _strip(cls, v: str) -> str:
        return "\n".join(line.strip() for line in v.strip().splitlines())


def get(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(f"SELECT key, value FROM meta WHERE key IN ({','.join('?' * len(DEFAULTS))})",
                        tuple(DEFAULTS)).fetchall()
    stored = {r["key"]: r["value"] for r in rows}
    return {k: stored.get(k, v) for k, v in DEFAULTS.items()}


def put(conn: sqlite3.Connection, s: SettingsIn) -> dict:
    with conn:
        for key, value in s.model_dump().items():
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    return get(conn)
