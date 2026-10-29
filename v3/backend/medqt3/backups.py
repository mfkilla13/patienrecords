"""Backups of the database: daily automatic, on demand, before a restore; an optional second copy elsewhere.

Copies are made with SQLite's online backup, so they are consistent while the program
is running, and each one is checked (PRAGMA quick_check) before it is kept. They live in
data/backups/ next to the database; if the doctor names a second folder (a flash drive,
another disk), every copy also goes there — the laptop's own disk can fail.

Restoring copies a backup *into* the open database (backup API in the other direction),
so no file is swapped under the running program; the current state is saved first.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import db as store

KIND_LABELS = {"auto": "автоматическая", "manual": "вручную", "before_restore": "перед восстановлением",
               "before_import": "перед переносом из 2.9", "before_update": "перед обновлением программы"}
NAME = re.compile(r"^medqt_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_(auto|manual|before_restore|before_import|before_update)\.db$")
KEEP_DAILY = 14          # newest automatic copies
KEEP_MONTHS = 12         # plus the last automatic copy of each of these months
KEEP_BEFORE = 10         # copies made before a restore or an import
EVERY = timedelta(hours=24)
META_EXTRA = "backup_extra_dir"


class BackupError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def folder(db_path: Path) -> Path:
    return Path(db_path).parent / "backups"


def extra_dir(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (META_EXTRA,)).fetchone()
    return row["value"] if row else ""


def set_extra_dir(conn: sqlite3.Connection, path: str) -> str:
    path = path.strip().strip('"')
    if path:
        p = Path(path)
        if not p.is_dir():
            raise BackupError(422, f"Папка «{path}» не найдена. Вставьте флешку или проверьте путь.")
        probe = p / ".medqt_write_test"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError:
            raise BackupError(422, f"В папку «{path}» нельзя записывать.")
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (META_EXTRA, path))
    return path


def _parse(p: Path) -> dict | None:
    m = NAME.match(p.name)
    if not m:
        return None
    at = datetime.fromisoformat(f"{m[1]}T{m[2]}:{m[3]}:{m[4]}")
    return {"name": p.name, "kind": m[5], "kindLabel": KIND_LABELS[m[5]], "at": at.isoformat(timespec="minutes"),
            "_at": at, "size": p.stat().st_size, "path": p}


def _all(db_path: Path) -> list[dict]:
    d = folder(db_path)
    items = [x for x in (_parse(p) for p in d.glob("medqt_*.db")) if x] if d.is_dir() else []
    return sorted(items, key=lambda x: x["_at"], reverse=True)


def _check(path: Path) -> None:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = c.execute("PRAGMA quick_check").fetchone()[0]
        c.execute("SELECT COUNT(*) FROM cases").fetchone()
    except sqlite3.DatabaseError as e:
        raise BackupError(500, f"Копия повреждена: {e}")
    finally:
        c.close()
    if result != "ok":
        raise BackupError(500, f"Копия не прошла проверку: {result}")


def prune(db_path: Path) -> list[str]:
    """Drop old automatic copies (keep the newest KEEP_DAILY and one per month) and old before-* copies."""
    items = _all(db_path)
    keep: set[str] = set()
    autos = [x for x in items if x["kind"] == "auto"]
    keep.update(x["name"] for x in autos[:KEEP_DAILY])
    months: dict[str, str] = {}
    for x in autos:                       # newest first, so the first seen is the month's last copy
        months.setdefault(x["_at"].strftime("%Y-%m"), x["name"])
    keep.update(list(months.values())[:KEEP_MONTHS])
    befores = [x for x in items if x["kind"].startswith("before_")]
    keep.update(x["name"] for x in befores[:KEEP_BEFORE])
    keep.update(x["name"] for x in items if x["kind"] == "manual")     # the doctor deletes those herself
    removed = []
    for x in items:
        if x["name"] not in keep:
            x["path"].unlink(missing_ok=True)
            removed.append(x["name"])
    return removed


def make(conn: sqlite3.Connection, db_path: Path, kind: str = "manual", now: datetime | None = None) -> dict:
    now = now or datetime.now()
    d = folder(db_path)
    d.mkdir(parents=True, exist_ok=True)
    name = f"medqt_{now:%Y-%m-%d_%H-%M-%S}_{kind}.db"
    target, part = d / name, d / (name + ".part")
    dst = sqlite3.connect(part)
    try:
        conn.backup(dst)
        # The copy inherits WAL mode from the live database; switch it back so the copy is one
        # self-contained file (no -wal/-shm beside it) that can be carried away and opened anywhere.
        dst.execute("PRAGMA journal_mode = DELETE")
    finally:
        dst.close()
    try:
        _check(part)
    except BackupError:
        part.unlink(missing_ok=True)
        raise
    part.replace(target)

    extra, extra_error = extra_dir(conn), None
    if extra:
        try:
            shutil.copy2(target, Path(extra) / name)
        except OSError as e:
            extra_error = f"Не удалось скопировать в «{extra}»: {e.strerror or e}"
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('backup_last', ?)", (now.isoformat(timespec="seconds"),))
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('backup_last_extra_error', ?)", (extra_error or "",))
    prune(db_path)
    return {"name": name, "extraError": extra_error}


def due(db_path: Path, now: datetime | None = None) -> bool:
    items = _all(db_path)
    return not items or (now or datetime.now()) - items[0]["_at"] >= EVERY


def listing(conn: sqlite3.Connection, db_path: Path) -> dict:
    items = _all(db_path)
    err = conn.execute("SELECT value FROM meta WHERE key = 'backup_last_extra_error'").fetchone()
    return {
        "folder": str(folder(db_path)),
        "extraDir": extra_dir(conn),
        "extraError": err["value"] if err and err["value"] else None,
        "last": items[0]["at"] if items else None,
        "items": [{k: v for k, v in x.items() if not k.startswith("_") and k != "path"} for x in items],
        "keep": {"daily": KEEP_DAILY, "months": KEEP_MONTHS},
    }


def restore(conn: sqlite3.Connection, db_path: Path, name: str) -> dict:
    src_path = folder(db_path) / name
    if not NAME.match(name) or not src_path.is_file():   # only our own files, never a path from outside
        raise BackupError(404, "Такой копии нет")
    _check(src_path)
    saved = make(conn, db_path, "before_restore")
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        src.backup(conn)
    finally:
        src.close()
    store.init_schema(conn)        # a copy from an older version gets any newer tables
    return {"restored": name, "savedAs": saved["name"]}


def delete(db_path: Path, name: str) -> None:
    p = folder(db_path) / name
    if not NAME.match(name) or not p.is_file():
        raise BackupError(404, "Такой копии нет")
    p.unlink()


def start_daily(conn: sqlite3.Connection, db_path: Path, check_every: float = 3600.0) -> threading.Thread:
    """A copy when the program starts (if the last one is a day old) and then once a day while it runs."""
    def loop() -> None:
        while True:
            try:
                if due(db_path):
                    make(conn, db_path, "auto")
            except Exception:          # a failed copy must never stop the program; the settings show the date
                pass
            time.sleep(check_every)

    t = threading.Thread(target=loop, name="medqt-backups", daemon=True)
    t.start()
    return t


def open_folder(db_path: Path) -> None:
    d = folder(db_path)
    d.mkdir(parents=True, exist_ok=True)
    os.startfile(d)  # type: ignore[attr-defined]   # Windows only, local folder
