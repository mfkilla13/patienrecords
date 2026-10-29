"""`MedQT.exe --self-test <file>`: checks a built program without opening its window.

Runs the real server on a throw-away database with the test patient and touches every part
that a build can lose: the bundled interface, fonts and dictionaries, PDF building, pdfium
previews, the Windows printer list. The result goes to <file> as text, one line per check.
"""

from __future__ import annotations

import json
import tempfile
import traceback
import urllib.request
from pathlib import Path


def run(out_path: str) -> None:
    lines: list[str] = []
    ok = True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            lines.append(f"OK   {name}: {fn()}")
        except Exception:
            ok = False
            lines.append(f"FAIL {name}: {traceback.format_exc(limit=3).strip().splitlines()[-1]}")

    try:
        from . import db as store
        from . import demo
        from .api import create_app
        from .desktop import _free_port, _wait_ready, start_server

        tmp = Path(tempfile.mkdtemp(prefix="medqt-selftest-"))
        conn = store.connect(tmp / "medqt.db")
        case_id = demo.create(conn)
        port = _free_port()
        server = start_server(create_app(tmp / "medqt.db"), port)
        base = f"http://127.0.0.1:{port}"
        _wait_ready(base)

        def get(path: str) -> bytes:
            with urllib.request.urlopen(base + path, timeout=30) as r:
                return r.read()

        def post(path: str, body: dict) -> dict:
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())

        check("интерфейс", lambda: f"{len(get('/'))} байт" if b'<div id="root">' in get("/") else 1 / 0)
        check("отделение", lambda: f"{len(json.loads(get('/api/department'))['patients'])} пациент(ов)")
        check("справочники", lambda: f"{len(json.loads(get('/api/dictionaries'))['ophthalmic'])} диагнозов")
        plan = json.loads(get(f"/api/cases/{case_id}/print-plan"))
        job = {}
        check("печать: PDF листа", lambda: job.update(post(f"/api/cases/{case_id}/print-jobs",
              {"recordIds": [r["id"] for r in plan["records"]], "mode": "new"})) or f"{len(job['pages'])} лист(а)")
        check("предпросмотр (pdfium)", lambda: f"{len(get(f'/api/print-jobs/{job['jobId']}/pages/1.png'))} байт PNG")
        check("принтеры Windows", lambda: ", ".join(json.loads(get("/api/printers"))["printers"]) or "не найдено ни одного")
        check("резервная копия", lambda: post("/api/backups", {})["name"])
        server.should_exit = True
    except Exception:
        ok = False
        lines.append("FAIL запуск: " + traceback.format_exc(limit=4).strip().splitlines()[-1])

    lines.insert(0, "MedQT self-test: " + ("всё в порядке" if ok else "ЕСТЬ ОШИБКИ"))
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
