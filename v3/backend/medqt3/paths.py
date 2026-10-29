"""Where MedQT keeps its files, in development and in the built Windows folder.

Built with PyInstaller the program is a portable folder:

    MedQT/MedQT.exe                  the launcher: starts the version named in versions/state.json
    MedQT/versions/3.0.1/MedQT.exe   the program itself, one folder per version (current and previous)
    MedQT/data/                      the database, its backups, the log — never touched by updates
    MedQT/updates/                   downloaded packages while an update is being installed

A program folder that is not inside versions/ (an old flat build, a copy elsewhere) keeps data/ next to itself.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
_SRC = Path(__file__).resolve().parent            # .../v3/backend/medqt3


def app_dir() -> Path:
    """The folder with MedQT.exe, or v3/ when running from the sources."""
    return Path(sys.executable).resolve().parent if FROZEN else _SRC.parents[1]


def installed() -> bool:
    """Running from MedQT/versions/<version>/ — the layout the updater can switch."""
    return FROZEN and app_dir().parent.name == "versions"


def install_root() -> Path:
    """The MedQT folder: the one with the launcher, data/ and versions/."""
    return app_dir().parents[1] if installed() else app_dir()


def data_dir() -> Path:
    env = os.environ.get("MEDQT_DATA")
    return Path(env) if env else install_root() / "data"


def frontend_dist() -> Path:
    return Path(getattr(sys, "_MEIPASS", "")) / "frontend" if FROZEN else app_dir() / "frontend" / "dist"
