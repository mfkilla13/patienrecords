"""MedQT.exe in the MedQT folder: starts the program version named in versions/state.json.

The desktop shortcut points here, so it never changes when the program updates: an update
only puts a new folder into versions/ and rewrites state.json. If the named version is
missing, the previous one (or the newest folder that has MedQT.exe) is started instead.

    MedQT.exe [--wait-pid <pid>] [args...]

--wait-pid: wait until that process has closed first (the program restarting itself after
an update or a rollback; only one copy may run at a time).
Standard library only — this file is bundled on its own and should stay small and unchanging.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


def _key(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else -1 for x in v.split("."))


def choose(root: Path) -> Path | None:
    versions = root / "versions"
    try:
        state = json.loads((versions / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    names = [state.get("current"), state.get("previous")]
    if versions.is_dir():
        names += sorted((d.name for d in versions.iterdir() if d.is_dir() and not d.name.endswith(".partial")),
                        key=_key, reverse=True)
    for name in names:
        if name and (versions / name / "MedQT.exe").is_file():
            return versions / name / "MedQT.exe"
    return None


def _wait(pid: int, timeout_ms: int = 30000) -> None:
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)        # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, timeout_ms)
        k.CloseHandle(h)


def _message(text: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "MedQT", 0x10)


def main() -> None:
    args = sys.argv[1:]
    if "--wait-pid" in args:
        i = args.index("--wait-pid")
        pid = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
        if pid.isdigit():
            _wait(int(pid))
    root = _root()
    exe = choose(root)
    if exe is None:
        _message(f"В папке «{root / 'versions'}» нет программы MedQT. Распакуйте архив MedQT заново (папку data не трогайте).")
        sys.exit(1)
    subprocess.Popen([str(exe), *args], cwd=str(exe.parent), close_fds=True)


if __name__ == "__main__":
    main()
