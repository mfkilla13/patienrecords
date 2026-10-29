"""Where MedQT keeps its files, in development and in the built Windows folder.

Built with PyInstaller the program is a portable folder, as 2.9 was: MedQT.exe, its
_internal/ files, and data/ next to the exe (the database and its backups). Updating
means replacing everything except data/.
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


def data_dir() -> Path:
    env = os.environ.get("MEDQT_DATA")
    return Path(env) if env else app_dir() / "data"


def frontend_dist() -> Path:
    return Path(getattr(sys, "_MEIPASS", "")) / "frontend" if FROZEN else app_dir() / "frontend" / "dist"
