import hashlib
import http.server
import json
import threading
import time
import zipfile
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medqt3 import backups, updater
from medqt3 import db as store
from medqt3.api import create_app


def _package(path: Path, version: str, ok: bool = True) -> Path:
    """An archive laid out like the real one: the launcher, and the program in versions/<version>/."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("MedQT/MedQT.exe", "launcher")
        z.writestr(f"MedQT/versions/{version}/MedQT.exe", "ok" if ok else "broken")
        z.writestr(f"MedQT/versions/{version}/_internal/base_library.zip", "x")
    return path


def _fake_selftest(app_dir: Path):
    good = (app_dir / "MedQT.exe").read_text() == "ok"
    return good, "MedQT self-test: " + ("всё в порядке" if good else "ЕСТЬ ОШИБКИ")


@pytest.fixture()
def github(tmp_path, monkeypatch):
    """A local stand-in for the GitHub releases API and its download links."""
    site = tmp_path / "site"
    site.mkdir()
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def publish(version: str, ok: bool = True, tag_prefix: str = "medqt3-", bad_sum: bool = False, extra: list | None = None):
        name = updater.package_name(version)
        pkg = _package(site / name, version, ok)
        digest = "0" * 64 if bad_sum else hashlib.sha256(pkg.read_bytes()).hexdigest()
        (site / (name + ".sha256")).write_text(f"{digest}  {name}\n")
        releases = (extra or []) + [{
            "tag_name": f"{tag_prefix}{version}", "draft": False, "prerelease": False, "body": "— исправлена печать",
            "published_at": "2026-11-02T10:00:00Z", "html_url": f"{base}/r",
            "assets": [{"name": name, "size": pkg.stat().st_size, "browser_download_url": f"{base}/{name}"},
                       {"name": name + ".sha256", "size": 80, "browser_download_url": f"{base}/{name}.sha256"}]}]
        (site / "releases.json").write_text(json.dumps(releases))
        return releases

    monkeypatch.setenv("MEDQT_UPDATE_URL", f"{base}/releases.json")
    yield publish
    srv.shutdown()


@pytest.fixture()
def installed(tmp_path):
    """An installed MedQT 3.0.0: launcher, versions/3.0.0, data/."""
    root = tmp_path / "MedQT"
    (root / "versions" / "3.0.0").mkdir(parents=True)
    (root / "versions" / "3.0.0" / "MedQT.exe").write_text("ok")
    (root / "versions" / "state.json").write_text(json.dumps({"current": "3.0.0"}))
    (root / "MedQT.exe").write_text("launcher")
    db_path = root / "data" / "medqt.db"
    db_path.parent.mkdir()
    store.connect(db_path).close()
    upd = updater.Updater(store.connect(db_path), db_path, root=root, current="3.0.0", selftest=_fake_selftest)
    client = TestClient(create_app(db_path, updates=upd))
    client.root, client.db_path = root, db_path
    return client


def _wait(client) -> dict:
    for _ in range(200):
        st = client.get("/api/update").json()
        if st["progress"] and st["progress"]["phase"] in ("ready", "error"):
            return st
        time.sleep(0.05)
    raise AssertionError("install did not finish")


def test_version_order():
    k = updater.version_key
    assert k("3.0.10") > k("3.0.9") > k("3.0.1") > k("3.0.1.dev2") > k("3.0.1.dev1") > k("3.0.0") > k("junk")


def test_only_v3_releases_with_a_package_count(github):
    old = [{"tag_name": "v2.9.8", "draft": False, "prerelease": False, "assets": [{"name": "MedQT-win.zip"}]},
           {"tag_name": "medqt3-9.9.9", "draft": True, "prerelease": False, "assets": []}]
    releases = github("3.0.1", extra=old)
    latest = updater.latest_release(releases)
    assert latest["version"] == "3.0.1" and latest["notes"] == "— исправлена печать"


def test_offline_check_is_quiet(installed, monkeypatch):
    monkeypatch.setenv("MEDQT_UPDATE_URL", "http://127.0.0.1:9/none")
    st = installed.post("/api/update/check").json()
    assert st["available"] is False and "Нет связи" in st["error"] and st["current"] == "3.0.0"


def test_download_installs_next_to_the_old_version_and_rolls_back(installed, github):
    github("3.0.1")
    st = installed.post("/api/update/check").json()
    assert st["available"] and st["latest"]["version"] == "3.0.1"
    installed.post("/api/update/download")
    st = _wait(installed)
    assert st["progress"]["phase"] == "ready", st["progress"]
    root = installed.root
    state = json.loads((root / "versions" / "state.json").read_text())
    assert state["current"] == "3.0.1" and state["previous"] == "3.0.0"
    assert (root / "versions" / "3.0.1" / "MedQT.exe").is_file() and (root / "versions" / "3.0.0" / "MedQT.exe").is_file()
    assert not (root / "versions" / "3.0.1.partial").exists()
    assert "before_update" in state["backup"] and (backups.folder(installed.db_path) / state["backup"]).is_file()
    assert (root / "data" / "medqt.db").is_file() and not list((root / "updates").glob("*.zip"))

    # the program running now is 3.0.0 in this test; going back means pointing the launcher at 3.0.0 again —
    # here «previous» is 3.0.0, the same schema, so the data stays
    assert st["rollback"]["version"] == "3.0.0" and st["rollback"]["needsDb"] is False
    installed.post("/api/update/rollback", json={"restoreDb": False})
    assert json.loads((root / "versions" / "state.json").read_text())["current"] == "3.0.0"


def test_a_broken_build_or_a_bad_checksum_is_not_installed(installed, github):
    github("3.0.1", bad_sum=True)
    installed.post("/api/update/check")
    installed.post("/api/update/download")
    st = _wait(installed)
    assert st["progress"]["phase"] == "error" and "контрольная сумма" in st["progress"]["text"]

    github("3.0.2", ok=False)
    installed.post("/api/update/check")
    installed.post("/api/update/download")
    st = _wait(installed)
    assert st["progress"]["phase"] == "error" and "самопроверку" in st["progress"]["text"]
    assert json.loads((installed.root / "versions" / "state.json").read_text())["current"] == "3.0.0"
    assert sorted(d.name for d in (installed.root / "versions").iterdir() if d.is_dir()) == ["3.0.0"]


def test_install_from_a_file(installed, tmp_path):
    data = _package(tmp_path / "x.zip", "3.1.0").read_bytes()
    installed.post("/api/update/file", content=data, headers={"Content-Type": "application/zip"})
    assert _wait(installed)["progress"]["phase"] == "ready"
    assert json.loads((installed.root / "versions" / "state.json").read_text())["current"] == "3.1.0"

    older = _package(tmp_path / "y.zip", "2.0.0").read_bytes()
    installed.post("/api/update/file", content=older)
    st = _wait(installed)
    assert st["progress"]["phase"] == "error" and "не новее" in st["progress"]["text"]
    installed.post("/api/update/file", content=b"not a zip")
    assert "не архив" in _wait(installed)["progress"]["text"]


def test_rollback_across_a_schema_change_restores_the_copy(installed, github):
    github("3.0.1")
    installed.post("/api/update/check")
    installed.post("/api/update/download")
    assert _wait(installed)["progress"]["phase"] == "ready"
    # pretend the copy was made by an older schema, then data was entered in the new version
    name = json.loads((installed.root / "versions" / "state.json").read_text())["backup"]
    import sqlite3
    c = sqlite3.connect(backups.folder(installed.db_path) / name)
    c.execute("PRAGMA user_version = 1")
    c.commit()
    c.close()
    info = installed.get("/api/update").json()["rollback"]
    assert info["needsDb"] is True
    r = installed.post("/api/update/rollback", json={"restoreDb": False})
    assert r.status_code == 409 and "копией базы" in r.json()["detail"]
    assert installed.post("/api/update/rollback", json={"restoreDb": True}).status_code == 200
    c = sqlite3.connect(installed.db_path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 1
    c.close()


def test_not_installed_program_only_checks(tmp_path, github):
    path = tmp_path / "t.db"
    store.connect(path).close()
    client = TestClient(create_app(path))
    github("9.0.0")
    st = client.post("/api/update/check").json()
    assert st["installable"] is False and st["available"] is True
    r = client.post("/api/update/download")
    assert r.status_code == 409 and "установленной" in r.json()["detail"]
