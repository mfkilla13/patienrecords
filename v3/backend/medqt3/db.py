"""SQLite storage.

Every table is sync-ready from day one: text UUID ids, created_at/updated_at
timestamps and soft delete (deleted_at), so the phone can later keep a copy
and merge changes back.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS patients (
    id          TEXT PRIMARY KEY,
    surname     TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    patronymic  TEXT NOT NULL DEFAULT '',
    dob         TEXT,                 -- YYYY-MM-DD
    city        TEXT NOT NULL DEFAULT '',
    street      TEXT NOT NULL DEFAULT '',
    house       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    legacy_id   INTEGER UNIQUE
);

CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    patient_id      TEXT NOT NULL REFERENCES patients(id),
    number          TEXT NOT NULL,     -- № истории болезни
    med_card        TEXT NOT NULL DEFAULT '',
    admitted_at     TEXT,              -- YYYY-MM-DDTHH:MM
    discharged_at   TEXT,
    archived_at     TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'discharged', 'archived')),
    outcome         TEXT NOT NULL DEFAULT '',
    dx_admission    TEXT NOT NULL DEFAULT '',
    dx_clinical     TEXT NOT NULL DEFAULT '',
    dx_final        TEXT NOT NULL DEFAULT '',
    dx_comorbid     TEXT NOT NULL DEFAULT '',
    recommendations TEXT NOT NULL DEFAULT '',
    discharge_json  TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT,
    legacy_id       INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS cases_patient ON cases(patient_id);
CREATE INDEX IF NOT EXISTS cases_status ON cases(status);

-- Records of a case: primary exam, diaries, protocols, discharge summary, ...
CREATE TABLE IF NOT EXISTS records (
    id           TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES cases(id),
    kind         TEXT NOT NULL,        -- primary_exam | diary | operation_protocol | plan | passport | discharge_summary | other
    recorded_at  TEXT NOT NULL,        -- YYYY-MM-DDTHH:MM[:SS]
    data_json    TEXT,                 -- structured form state
    html_legacy  TEXT,                 -- printable HTML carried over from 2.9.x
    legacy_json  TEXT,                 -- old columns kept verbatim (diagnosis, treatment, diag_*)
    printed_at   TEXT,
    print_batch  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT,
    legacy_id    INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS records_case ON records(case_id, recorded_at);

CREATE TABLE IF NOT EXISTS studies (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases(id),
    kind        TEXT NOT NULL,
    study_date  TEXT,                  -- YYYY-MM-DD
    data_json   TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    legacy_id   INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS studies_case ON studies(case_id);

CREATE TABLE IF NOT EXISTS prescriptions (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL REFERENCES cases(id),
    category    TEXT NOT NULL DEFAULT '',   -- stol | exam | drugs | lfk
    name        TEXT NOT NULL,
    method      TEXT NOT NULL DEFAULT '',
    freq        TEXT NOT NULL DEFAULT '',
    date_from   TEXT,
    date_to     TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT,
    legacy_id   INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS prescriptions_case ON prescriptions(case_id);

-- Where the last diary print ended, so new records continue the same sheet.
-- end_mm is measured from the top edge of the paper.
CREATE TABLE IF NOT EXISTS print_state (
    case_id         TEXT PRIMARY KEY REFERENCES cases(id),
    sheet           INTEGER NOT NULL DEFAULT 1,
    used_mm         REAL NOT NULL DEFAULT 0,
    last_printed_at TEXT,
    last_batch      TEXT,
    source          TEXT NOT NULL DEFAULT 'v3',   -- 'legacy' = carried over from 2.9, meaning differs
    updated_at      TEXT NOT NULL
);

-- Primary exam templates the doctor saves: everything except measurements and the patient's diagnoses.
CREATE TABLE IF NOT EXISTS exam_templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    keywords    TEXT NOT NULL DEFAULT '',   -- matched against the admission diagnosis to suggest it
    data_json   TEXT NOT NULL,
    use_count   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    deleted_at  TEXT
);

-- The fixed place of every record printed by v3: reprints go exactly there, new records go below.
CREATE TABLE IF NOT EXISTS print_positions (
    record_id    TEXT PRIMARY KEY REFERENCES records(id),
    start_sheet  INTEGER NOT NULL,
    start_mm     REAL NOT NULL,          -- from the top edge of the paper
    end_sheet    INTEGER NOT NULL,
    end_mm       REAL NOT NULL,
    job_id       TEXT,
    updated_at   TEXT NOT NULL
);

-- Every print attempt. Records are marked printed only after the doctor confirms the sheet came out right.
-- kind 'sheet': new records below the last print + reprints in their own places; 'copy': selected records
-- one after another, nothing is marked.
CREATE TABLE IF NOT EXISTS print_jobs (
    id           TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES cases(id),
    kind         TEXT NOT NULL DEFAULT 'sheet' CHECK (kind IN ('sheet', 'copy')),
    record_ids   TEXT NOT NULL,          -- JSON list
    placements   TEXT NOT NULL,          -- JSON: [{recordId, isNew, startSheet, startMm, endSheet, endMm}]
    pages        TEXT NOT NULL,          -- JSON: [{sheet, insert, shade: [[top_mm, bottom_mm], ...]}]
    new_end_sheet INTEGER,
    new_end_mm   REAL,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'cancelled')),
    printer      TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS print_jobs_case ON print_jobs(case_id);
"""


def new_id() -> str:
    return uuid.uuid4().hex


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_db_path() -> Path:
    env = os.environ.get("MEDQT_DB")
    if env:
        return Path(env)
    from .paths import data_dir
    return data_dir() / "medqt.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or default_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"База создана более новой версией программы (схема {version}).")
    with conn:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
