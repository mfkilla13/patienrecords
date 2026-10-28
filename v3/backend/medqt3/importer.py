"""Import a 2.9.x `patients.db` into the MedQT 3 database.

The old file is opened read-only and never modified. Nothing is dropped:
structured form state goes to data_json, the printable HTML to html_legacy,
and every other old column to legacy_json. Each row keeps its old id in
legacy_id so the import can be checked row by row.

Usage:
    python -m medqt3.importer path/to/patients.db [--db path/to/medqt.db] [--force]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from . import db as store

_DMY = re.compile(r"^\s*(\d{1,2})[.,](\d{1,2})[.,](\d{2,4})\s*$")
_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})")


def to_date(value: str | None) -> str | None:
    """'1.04.2026' / '16.04.2026' / '2026-04-16...' -> '2026-04-16'."""
    if not value:
        return None
    m = _ISO.match(value)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = _DMY.match(value)
    if m:
        year = int(m[3])
        if year < 100:
            year += 2000
        return f"{year:04d}-{int(m[2]):02d}-{int(m[1]):02d}"
    return None


def to_datetime(date: str | None, time: str | None, fallback: str | None = None) -> str | None:
    d = to_date(date)
    if not d:
        return fallback[:16] if fallback else None
    t = (time or "").strip()
    return f"{d}T{t}" if re.fullmatch(r"\d{2}:\d{2}", t) else d


def _json_or_none(text: str | None):
    if not text or not text.lstrip().startswith("{"):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _latest_nonempty(rows, key: str) -> str:
    for r in sorted(rows, key=lambda r: r["visit_date"] or "", reverse=True):
        if (r[key] or "").strip():
            return r[key].strip()
    return ""


def import_legacy(old_path: Path, conn: sqlite3.Connection, as_unprinted: bool = False) -> dict:
    """as_unprinted: for trying printing on real histories — print marks and 2.9 sheet positions are
    left out, so every record can be printed by v3 from the first sheet. Never use for the real move."""
    old = sqlite3.connect(f"file:{Path(old_path).as_posix()}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    ts = store.now_iso()
    patient_ids: dict[int, str] = {}
    case_ids: dict[int, str] = {}

    with conn:
        for p in old.execute("SELECT * FROM patients ORDER BY id"):
            pid = store.new_id()
            patient_ids[p["id"]] = pid
            house = ", кв. ".join(x for x in [(p["house"] or "").strip(), (p["apartment"] or "").strip()] if x)
            created = p["created_at"] or ts
            conn.execute(
                "INSERT INTO patients (id, surname, name, patronymic, dob, city, street, house,"
                " created_at, updated_at, legacy_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, (p["surname"] or "").strip(), (p["name"] or "").strip(), (p["patronymic"] or "").strip(),
                 to_date(p["dob"]), (p["city"] or "").strip(), (p["street"] or "").strip(), house,
                 created, ts, p["id"]),
            )

        histories = old.execute("SELECT * FROM histories").fetchall()
        by_case: dict[int, list] = {}
        for h in histories:
            by_case.setdefault(h["history_id"], []).append(h)

        for c in old.execute("SELECT * FROM medical_cases ORDER BY id"):
            cid = store.new_id()
            case_ids[c["id"]] = cid
            recs = by_case.get(c["id"], [])
            discharge = None
            if c["discharge_summary"]:
                discharge = json.dumps({"epicrisis": c["discharge_summary"]}, ensure_ascii=False)
            conn.execute(
                "INSERT INTO cases (id, patient_id, number, med_card, admitted_at, discharged_at, archived_at,"
                " status, outcome, dx_admission, dx_clinical, dx_final, dx_comorbid, recommendations,"
                " discharge_json, created_at, updated_at, legacy_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, patient_ids[c["patient_id"]], (c["card_number"] or "").strip(),
                 (c["medical_record_number"] or "").strip(),
                 to_datetime(c["admission_date"], c["admission_time"], c["created_at"]),
                 to_datetime(c["discharge_date"], c["discharge_time"]),
                 c["closed_at"] if c["status"] == "archived" else None,
                 c["status"] or "active", (c["outcome"] or "").strip(),
                 _latest_nonempty(recs, "diag_admission"), _latest_nonempty(recs, "diag_clinical"),
                 (c["final_diagnosis"] or "").strip(), _latest_nonempty(recs, "diag_comorbid"),
                 (c["recommendations"] or "").strip(), discharge,
                 c["created_at"] or ts, ts, c["id"]),
            )

        for h in histories:
            data = _json_or_none(h["notes"])
            legacy = {k: h[k] for k in ("diagnosis", "treatment", "diag_admission", "diag_clinical",
                                        "diag_comorbid", "printed", "print_top_offset_mm") if h[k] not in (None, "")}
            if h["notes"] and data is None:
                legacy["notes"] = h["notes"]
            conn.execute(
                "INSERT INTO records (id, case_id, kind, recorded_at, data_json, html_legacy, legacy_json,"
                " printed_at, print_batch, created_at, updated_at, legacy_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (store.new_id(), case_ids[h["history_id"]], h["record_type"] or "other",
                 h["visit_date"] or ts,
                 json.dumps(data, ensure_ascii=False) if data is not None else None,
                 h["examination"], json.dumps(legacy, ensure_ascii=False) if legacy else None,
                 None if as_unprinted else h["printed_at"], None if as_unprinted else h["print_batch_id"],
                 h["visit_date"] or ts, ts, h["id"]),
            )

        for d in old.execute("SELECT * FROM diagnostics"):
            data = _json_or_none(d["results"]) or {"schema": "free_text", "name": d["name"], "text": d["results"]}
            if d["study_date"] and not to_date(d["study_date"]):
                # Typos like "20.0432026" are kept as typed for the doctor to fix, never guessed.
                data["unparsed_date"] = d["study_date"]
            conn.execute(
                "INSERT INTO studies (id, case_id, kind, study_date, data_json, created_at, updated_at, legacy_id)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (store.new_id(), case_ids[d["history_id"]], (d["name"] or "").strip(), to_date(d["study_date"]),
                 json.dumps(data, ensure_ascii=False), d["created_at"] or ts, ts, d["id"]),
            )

        record_case = {h["id"]: h["history_id"] for h in histories}
        for a in old.execute("SELECT * FROM appointments"):
            conn.execute(
                "INSERT INTO prescriptions (id, case_id, name, method, freq, date_from, date_to,"
                " created_at, updated_at, legacy_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (store.new_id(), case_ids[record_case[a["history_id"]]], a["name"] or "", a["method"] or "",
                 a["freq"] or "", to_date(a["date_assign"]), to_date(a["date_cancel"]),
                 a["created_at"] or ts, ts, a["id"]),
            )

        for s in [] if as_unprinted else old.execute("SELECT * FROM case_print_state"):
            if s["case_id"] in case_ids:
                conn.execute(
                    "INSERT INTO print_state (case_id, used_mm, last_printed_at, last_batch, source, updated_at)"
                    " VALUES (?,?,?,?,'legacy',?)",
                    (case_ids[s["case_id"]], s["diary_current_page_used_mm"] or 0,
                     s["diary_last_printed_at"], s["diary_last_batch_id"], ts),
                )

        conn.execute("INSERT OR REPLACE INTO meta VALUES ('imported_from', ?)", (str(old_path),))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('imported_at', ?)", (ts,))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('imported_as_unprinted', ?)", ("1" if as_unprinted else "0",))

    counts = {}
    tables = [("patients", "patients"), ("medical_cases", "cases"), ("histories", "records"),
              ("diagnostics", "studies"), ("appointments", "prescriptions")]
    if not as_unprinted:
        tables.append(("case_print_state", "print_state"))
    for old_table, new_table in tables:
        counts[new_table] = (old.execute(f"SELECT COUNT(*) FROM {old_table}").fetchone()[0],
                             conn.execute(f"SELECT COUNT(*) FROM {new_table}").fetchone()[0])
    old.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Перенос данных из MedQT 2.9.x")
    ap.add_argument("old_db", type=Path)
    ap.add_argument("--db", type=Path, default=None, help="куда писать (по умолчанию v3/data/medqt.db)")
    ap.add_argument("--force", action="store_true", help="перезаписать существующую новую базу")
    ap.add_argument("--as-unprinted", action="store_true",
                    help="для проверки печати: перенести все записи как ненапечатанные (не для настоящего переноса)")
    args = ap.parse_args(argv)

    target = args.db or store.default_db_path()
    if target.exists():
        if not args.force:
            print(f"{target} уже существует. Добавьте --force, чтобы перезаписать.", file=sys.stderr)
            return 1
        # Remove the WAL side files too: a stale -wal would be replayed into the new database.
        for suffix in ("", "-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
    conn = store.connect(target)
    counts = import_legacy(args.old_db, conn, as_unprinted=args.as_unprinted)
    if args.as_unprinted:
        print("Режим проверки печати: все записи перенесены как ненапечатанные.")
    ok = True
    for table, (was, now) in counts.items():
        mark = "ok" if was == now else "РАСХОЖДЕНИЕ"
        ok &= was == now
        print(f"{table:14} было {was:4}  стало {now:4}  {mark}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
