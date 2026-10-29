"""Desktop entry point: local server plus its own window (no browser tab).

The server listens on 127.0.0.1 only; the phone link will be added later
as a separate, explicitly enabled listener.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request

from . import paths


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


def _message(text: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "MedQT", 0x40)


def _single_instance():
    """Two copies at once would both print onto the same sheet positions; the second one just says so."""
    import msvcrt
    lock = open(paths.data_dir() / ".medqt.lock", "a+")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        _message("MedQT уже открыт. Найдите его окно на панели задач.")
        sys.exit(0)
    return lock          # kept open (and locked) while the program runs


def start_server(app, port: int):
    import uvicorn

    # log_config=None: uvicorn's default colour formatter needs a console, the built program has none.
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    return server


def main() -> None:
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:            # built without a console: keep errors where they can be read later
        sys.stdout = sys.stderr = open(paths.data_dir() / "medqt.log", "a", encoding="utf-8", buffering=1)
    if "--self-test" in sys.argv:
        from .selftest import run
        run(sys.argv[sys.argv.index("--self-test") + 1])
        return
    lock = _single_instance()  # noqa: F841

    import webview
    from .api import create_app

    port = _free_port()
    app = create_app(auto_backup=True)
    server = start_server(app, port)
    url = f"http://127.0.0.1:{port}"
    _wait_ready(url)
    webview.settings["ALLOW_DOWNLOADS"] = True    # «Выгрузить в Excel» asks where to save the file
    window = webview.create_window("MedQT", url, width=1440, height=940, min_size=(1024, 700))
    app.state.on_quit = window.destroy          # «Перезапустить» after an update
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    main()
