"""Program updates from GitHub releases, and going back to the previous version.

Releases of v3 are tagged «medqt3-<version>» (never «v…»: those belong to 2.9 and start its own build) and carry
two files: MedQT-<version>-win.zip, the same archive as for a fresh install, and its .sha256. The repository is
public, so the laptop needs no token — only a connection (the phone's hotspot is enough) and the doctor's click.

Installing never touches the running program: the new version is unpacked into versions/<version>.partial,
checked with its own `--self-test`, the database is copied to backups («перед обновлением программы»), and
only then the folder is renamed and versions/state.json points the launcher at it. The previous version
stays next to it; going back rewrites state.json the other way. If the newer version changed the database
schema, the older one cannot open it, so going back also restores the copy made before the update.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import __version__, backups, paths
from . import db as store

REPO = "mfkilla13/patienrecords"
TAG_PREFIX = "medqt3-"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
CHECK_EVERY = 6 * 3600           # an automatic check at most this often; «Проверить сейчас» always asks
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$")


class UpdateError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def version_key(v: str) -> tuple:
    """3.0.1 > 3.0.1.dev2 > 3.0.0; anything unreadable is the oldest."""
    m = VERSION.match(v or "")
    if not m:
        return (-1,)
    return (int(m[1]), int(m[2]), int(m[3]), 0 if m[4] is not None else 1, int(m[4] or 0))


def package_name(v: str) -> str:
    return f"MedQT-{v}-win.zip"


def releases_url() -> str:
    return os.environ.get("MEDQT_UPDATE_URL") or RELEASES_URL


def _tls() -> ssl.SSLContext:
    """Windows' own certificates plus certifi's: a laptop that rarely goes online may lack the intermediate
    certificate GitHub's chain needs (Windows fetches it lazily, Python cannot), and the check then fails."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except (ImportError, OSError):
        pass
    return ctx


def _get(url: str, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"User-Agent": f"MedQT/{__version__}", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout, context=_tls())


def latest_release(releases: list) -> dict | None:
    """The newest published v3 release that has the package attached."""
    best = None
    for r in releases if isinstance(releases, list) else []:
        tag = r.get("tag_name") or ""
        if r.get("draft") or r.get("prerelease") or not tag.startswith(TAG_PREFIX):
            continue
        v = tag[len(TAG_PREFIX):]
        if not VERSION.match(v):
            continue
        assets = {a.get("name"): a for a in r.get("assets") or []}
        pkg, sha = assets.get(package_name(v)), assets.get(package_name(v) + ".sha256")
        if not pkg or not sha:
            continue
        if best is None or version_key(v) > version_key(best["version"]):
            best = {"version": v, "notes": (r.get("body") or "").strip(), "publishedAt": (r.get("published_at") or "")[:10],
                    "size": pkg.get("size") or 0, "url": pkg.get("browser_download_url"),
                    "shaUrl": sha.get("browser_download_url"), "page": r.get("html_url") or ""}
    return best


def default_selftest(app_dir: Path) -> tuple[bool, str]:
    """Run the unpacked version's own self-test on a throw-away data folder."""
    tmp = Path(tempfile.mkdtemp(prefix="medqt-update-test-"))
    report = tmp / "selftest.txt"
    try:
        subprocess.run([str(app_dir / "MedQT.exe"), "--self-test", str(report)], cwd=str(app_dir), timeout=300,
                       env={**os.environ, "MEDQT_DATA": str(tmp / "data")}, check=False)
        text = report.read_text(encoding="utf-8") if report.is_file() else "самопроверка не создала отчёт"
        return ("ЕСТЬ ОШИБКИ" not in text and report.is_file()), text
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"самопроверка не запустилась: {e}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Updater:
    def __init__(self, conn: sqlite3.Connection, db_path: Path, root: Path | None = None, current: str = __version__,
                 selftest: Callable[[Path], tuple[bool, str]] = default_selftest):
        self.conn, self.db_path = conn, db_path
        self.installable = root is not None or paths.installed()
        self.root = root or paths.install_root()
        self.current = current
        self.selftest = selftest
        self.last: dict | None = None          # the last check: {checkedAt, latest, error}
        self.progress: dict | None = None      # the install in progress or just finished
        self._lock = threading.Lock()

    # ---- state.json: which version the launcher starts ----
    @property
    def versions(self) -> Path:
        return self.root / "versions"

    def state(self) -> dict:
        try:
            return json.loads((self.versions / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_state(self, state: dict) -> None:
        self.versions.mkdir(parents=True, exist_ok=True)
        tmp = self.versions / "state.json.part"
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.versions / "state.json")

    # ---- checking ----
    def check(self, force: bool = False) -> dict:
        if not force and self.last and time.time() - self.last["_at"] < CHECK_EVERY and not self.last["error"]:
            return self.last
        result = {"_at": time.time(), "checkedAt": datetime.now().isoformat(timespec="minutes"), "latest": None, "error": None}
        try:
            with _get(releases_url()) as r:
                result["latest"] = latest_release(json.loads(r.read().decode("utf-8")))
        except (urllib.error.URLError, OSError):
            result["error"] = "Нет связи с GitHub — проверьте интернет (можно через телефон)."
        except ValueError:
            result["error"] = "GitHub ответил непонятно — попробуйте позже."
        self.last = result
        return result

    def check_later(self, delay: float = 5.0) -> None:
        """The automatic check after start: in the background, silent when offline."""
        threading.Thread(target=lambda: (time.sleep(delay), self.check()), daemon=True).start()

    def rollback_info(self) -> dict | None:
        s = self.state()
        prev = s.get("previous")
        if not self.installable or not prev or not (self.versions / prev / "MedQT.exe").is_file():
            return None
        backup = s.get("backup") or ""
        path = backups.folder(self.db_path) / backup if backup else None
        schema = None
        if path and path.is_file():
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                schema = c.execute("PRAGMA user_version").fetchone()[0]
            finally:
                c.close()
        return {"version": prev, "backup": backup if schema is not None else None,
                "backupAt": s.get("updatedAt"), "needsDb": schema is not None and schema < store.SCHEMA_VERSION}

    def status(self) -> dict:
        last = self.last or {}
        latest = last.get("latest")
        return {
            "current": self.current,
            "installable": self.installable,
            "checkedAt": last.get("checkedAt"),
            "error": last.get("error"),
            "latest": latest,
            "available": bool(latest and version_key(latest["version"]) > version_key(self.current)),
            "progress": self.progress,
            "rollback": self.rollback_info(),
        }

    # ---- installing ----
    def _busy(self) -> bool:
        return bool(self.progress and self.progress["phase"] not in ("ready", "error"))

    def _set(self, phase: str, text: str, **kw) -> None:
        self.progress = {"phase": phase, "text": text, "done": 0, "total": 0, **kw}

    def _start(self, work: Callable[[], None]) -> dict:
        if not self.installable:
            raise UpdateError(409, "Обновление ставится только в установленной программе (папка MedQT с versions\\).")
        with self._lock:
            if self._busy():
                raise UpdateError(409, "Обновление уже устанавливается.")
            self._set("start", "Начинаем…")

        def run() -> None:
            try:
                work()
            except UpdateError as e:
                self._set("error", e.message)
            except Exception as e:           # keep the program running, show what happened
                self._set("error", f"Не удалось обновить: {e}")
        threading.Thread(target=run, daemon=True).start()
        return self.status()

    def download(self) -> dict:
        latest = (self.last or {}).get("latest")
        if not latest or version_key(latest["version"]) <= version_key(self.current):
            raise UpdateError(409, "Новой версии нет — сначала «Проверить сейчас».")
        return self._start(lambda: self._download_and_install(latest))

    def install_file(self, data: bytes) -> dict:
        if not self.installable:
            raise UpdateError(409, "Обновление ставится только в установленной программе (папка MedQT с versions\\).")
        updates = self.root / "updates"
        updates.mkdir(parents=True, exist_ok=True)
        path = updates / "from-file.zip"
        path.write_bytes(data)
        return self._start(lambda: self._install(path, None))

    def _download_and_install(self, latest: dict) -> None:
        updates = self.root / "updates"
        updates.mkdir(parents=True, exist_ok=True)
        target = updates / package_name(latest["version"])
        part = target.with_suffix(".part")
        self._set("download", "Скачиваем…", total=latest["size"])
        try:
            with _get(latest["shaUrl"], timeout=30) as r:
                expected = r.read().decode("ascii", "replace").split()[0].lower()
            digest = hashlib.sha256()
            with _get(latest["url"], timeout=60) as r, open(part, "wb") as f:
                while chunk := r.read(256 * 1024):
                    f.write(chunk)
                    digest.update(chunk)
                    self.progress["done"] += len(chunk)
        except (urllib.error.URLError, OSError):
            part.unlink(missing_ok=True)
            raise UpdateError(502, "Связь прервалась при скачивании — попробуйте ещё раз.")
        if digest.hexdigest() != expected:
            part.unlink(missing_ok=True)
            raise UpdateError(502, "Архив скачался с ошибкой (контрольная сумма не совпала) — попробуйте ещё раз.")
        part.replace(target)
        self._install(target, latest["version"])

    def _install(self, zip_path: Path, expected: str | None) -> None:
        self._set("unpack", "Распаковываем…")
        try:
            z = zipfile.ZipFile(zip_path)
        except (zipfile.BadZipFile, OSError):
            raise UpdateError(422, "Это не архив MedQT.")
        with z:
            found = {n.split("/")[2] for n in z.namelist() if n.startswith("MedQT/versions/") and n.count("/") >= 3}
            found = {v for v in found if VERSION.match(v)}
            if len(found) != 1:
                raise UpdateError(422, "В архиве нет программы MedQT 3.")
            v = found.pop()
            if expected and v != expected:
                raise UpdateError(422, f"В архиве версия {v}, а ожидалась {expected}.")
            if version_key(v) <= version_key(self.current):
                raise UpdateError(409, f"В архиве версия {v} — она не новее установленной ({self.current}).")
            if z.testzip() is not None:
                raise UpdateError(422, "Архив повреждён.")
            dest = self.versions / f"{v}.partial"
            shutil.rmtree(dest, ignore_errors=True)
            prefix = f"MedQT/versions/{v}/"
            base = dest.resolve()
            for info in z.infolist():
                if not info.filename.startswith(prefix) or info.is_dir():
                    continue
                out = (dest / info.filename[len(prefix):]).resolve()
                if base not in out.parents:          # a name like ../../x would write outside the folder
                    raise UpdateError(422, "Архив повреждён.")
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(out, "wb") as f:
                    shutil.copyfileobj(src, f)
        if not (dest / "MedQT.exe").is_file():
            shutil.rmtree(dest, ignore_errors=True)
            raise UpdateError(422, "В архиве нет MedQT.exe.")

        self._set("test", f"Проверяем версию {v}…")
        ok, report = self.selftest(dest)
        if not ok:
            shutil.rmtree(dest, ignore_errors=True)
            raise UpdateError(500, f"Новая версия не прошла самопроверку и не установлена. {report[:300]}")

        self._set("backup", "Сохраняем копию базы…")
        saved = backups.make(self.conn, self.db_path, "before_update")

        final = self.versions / v
        shutil.rmtree(final, ignore_errors=True)
        dest.rename(final)
        self._write_state({"current": v, "previous": self.current, "backup": saved["name"],
                           "updatedAt": datetime.now().isoformat(timespec="minutes")})
        keep = {v, self.current}
        for d in self.versions.iterdir():
            if d.is_dir() and d.name not in keep:
                shutil.rmtree(d, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        self._set("ready", f"Версия {v} установлена. Перезапустите программу.", version=v)

    # ---- going back ----
    def rollback(self, restore_db: bool) -> dict:
        info = self.rollback_info()
        if not info:
            raise UpdateError(409, "Прежней версии нет.")
        if info["needsDb"] and not restore_db:
            raise UpdateError(409, "Версия {} не откроет нынешнюю базу — вернуть её можно только вместе с копией базы.".format(info["version"]))
        if restore_db:
            if not info["backup"]:
                raise UpdateError(409, "Копии базы перед обновлением нет.")
            backups.make(self.conn, self.db_path, "before_restore")
            src = sqlite3.connect(f"file:{backups.folder(self.db_path) / info['backup']}?mode=ro", uri=True)
            try:
                src.backup(self.conn)           # as it was, schema included: the older version opens it
            finally:
                src.close()
        self._write_state({"current": info["version"], "previous": self.current, "backup": None,
                           "updatedAt": datetime.now().isoformat(timespec="minutes")})
        self._set("ready", f"Будет запущена версия {info['version']}. Перезапустите программу.", version=info["version"])
        return self.status()

    def restart(self) -> None:
        """Start the launcher, which waits for this process to close and then opens the version in state.json."""
        launcher = self.root / "MedQT.exe"
        if not self.installable or not launcher.is_file():
            raise UpdateError(409, "Перезапустите программу вручную.")
        subprocess.Popen([str(launcher), "--wait-pid", str(os.getpid())], cwd=str(self.root), close_fds=True)
