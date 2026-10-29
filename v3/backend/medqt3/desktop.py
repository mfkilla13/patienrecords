"""Desktop entry point: local server plus its own window (no browser tab).

The server listens on 127.0.0.1 only; the phone link will be added later
as a separate, explicitly enabled listener.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from .api import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Сервер MedQT не запустился.")


def main() -> None:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    _wait_ready(url)
    webview.settings["ALLOW_DOWNLOADS"] = True    # «Выгрузить в Excel» asks where to save the file
    webview.create_window("MedQT", url, width=1440, height=940, min_size=(1024, 700))
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    main()
