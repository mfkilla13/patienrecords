"""The doctor's dictionaries: diagnoses, comorbid diagnoses, examinations, treatment basis, addresses.

The lists shipped with the program (medqt3/dictdata, taken from 2.9) are the starting point;
once the doctor edits a dictionary, her version is kept in the meta table, so it lives in the
database, goes into every backup and is never overwritten by an update of the program.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .clinical import TREATMENT_LABELS

DICT_DIR = Path(__file__).resolve().parent / "dictdata"

# name -> (file name, the same as in 2.9's data folder; title)
FILES = {
    "ophthalmic": ("ophthalmic_diagnoses.json", "Диагнозы — глаза"),
    "comorbid": ("comorbid_diagnoses.json", "Сопутствующие диагнозы"),
    "examinations": ("examinations.json", "Обследования"),
    "treatment": ("treatment_basis.json", "Обоснование лечения"),
    "addresses": ("addresses.json", "Адреса"),
}
LISTS = ("ophthalmic", "comorbid", "examinations")
ADDRESS_GROUPS = {"cities": "Населённые пункты", "streets": "Улицы", "villages": "Сёла — для отчёта"}
# addresses.json has every settlement of Приднестровье (the state register, as listed on Wikipedia in 2026)
# under "cities", and its villages under "villages": patients from those count as «сельские жители» in the
# department report. Посёлки (Маяк, Первомайск, Красное...) are counted as towns; the doctor corrects the list.
HINTS = {
    "ophthalmic": "Подсказки диагнозов OD/OS/OU при поступлении, в первичном осмотре и выписке.",
    "comorbid": "Подсказки сопутствующих диагнозов.",
    "examinations": "План обследования в первичном осмотре; по нему строится список «ещё не внесены» в исследованиях.",
    "treatment": "Препараты по группам для «Обоснования лечения» в первичном осмотре и дневниках.",
    "addresses": "Подсказки при поступлении (пункты и улицы из базы подсказываются и так). «Сёла» — кого считать сельскими жителями в отчёте отделения.",
}
MAX_ITEMS = 2000
MAX_LEN = 300


class DictError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _key(name: str) -> str:
    return f"dict_{name}"


def bundled(name: str):
    return json.loads((DICT_DIR / FILES[name][0]).read_text(encoding="utf-8"))


def _clean_list(items) -> list[str]:
    if not isinstance(items, list):
        raise DictError(422, "Ожидался список")
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if not isinstance(x, str):
            continue
        x = " ".join(x.split())[:MAX_LEN]
        if x and x.casefold() not in seen:
            seen.add(x.casefold())
            out.append(x)
    if len(out) > MAX_ITEMS:
        raise DictError(422, f"Слишком длинный список (больше {MAX_ITEMS})")
    return out


def clean(name: str, value):
    """Trimmed, without empty lines and repeats (ignoring case), in the shape of that dictionary."""
    if name not in FILES:
        raise DictError(404, "Нет такого справочника")
    if name in LISTS:
        return _clean_list(value)
    if not isinstance(value, dict):
        raise DictError(422, "Ожидались группы")
    if name == "addresses":
        return {k: _clean_list(value.get(k, [])) for k in ADDRESS_GROUPS}
    groups = bundled("treatment")          # the groups are fixed: diaries and exams refer to them by key
    return {g: _clean_list(value.get(g, [])) for g in groups}


def get(conn: sqlite3.Connection, name: str):
    if name not in FILES:
        raise DictError(404, "Нет такого справочника")
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (_key(name),)).fetchone()
    if row:
        value = json.loads(row["value"])
        if name == "addresses" and "villages" not in value:     # saved before the list existed
            value["villages"] = clean(name, bundled(name))["villages"]
        return value
    return clean(name, bundled(name))


def groups(name: str) -> dict[str, str] | None:
    if name == "treatment":
        return {g: TREATMENT_LABELS.get(g, g) for g in bundled("treatment")}
    if name == "addresses":
        return dict(ADDRESS_GROUPS)
    return None


def info(conn: sqlite3.Connection, name: str) -> dict:
    """A dictionary as the editor shows it."""
    value = get(conn, name)
    return {"name": name, "title": FILES[name][1], "hint": HINTS[name], "groups": groups(name),
            "value": value, "edited": name in edited(conn), "canReset": True}


def edited(conn: sqlite3.Connection) -> set[str]:
    keys = [_key(n) for n in FILES]
    rows = conn.execute(f"SELECT key FROM meta WHERE key IN ({','.join('?' * len(keys))})", keys).fetchall()
    return {r["key"][len("dict_"):] for r in rows}


def put(conn: sqlite3.Connection, name: str, value):
    value = clean(name, value)
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                     (_key(name), json.dumps(value, ensure_ascii=False)))
    return value


def reset(conn: sqlite3.Connection, name: str):
    if name not in FILES:
        raise DictError(404, "Нет такого справочника")
    with conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (_key(name),))
    return get(conn, name)


def _union(have: list[str], extra: list[str]) -> tuple[list[str], int]:
    seen = {x.casefold() for x in have}
    added = [x for x in extra if x.casefold() not in seen]
    return have + added, len(added)


def merge(conn: sqlite3.Connection, name: str, value) -> int:
    """Add what a 2.9 dictionary file has and ours lacks (as 2.9 itself merged its own and the user's file).
    Nothing is removed. Returns how many entries were added."""
    incoming = clean(name, value)
    have = get(conn, name)
    if name in LISTS:
        merged, n = _union(have, incoming)
    else:
        merged, n = {}, 0
        for g in have:
            merged[g], k = _union(have[g], incoming.get(g, []))
            n += k
    if n:
        put(conn, name, merged)
    return n

