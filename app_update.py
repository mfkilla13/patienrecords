import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from app_version import APP_VERSION


UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/mfkilla13/patienrecords/main/update/version.json"


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    notes: str = ""
    package_type: str = "zip"


def _version_tuple(value):
    parts = []
    for item in str(value or "").strip().split("."):
        try:
            parts.append(int(item))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_newer_version(remote_version, current_version=APP_VERSION):
    return _version_tuple(remote_version) > _version_tuple(current_version)


def fetch_update_info(url=UPDATE_MANIFEST_URL, timeout=5):
    request = Request(url, headers={"User-Agent": f"MedQT/{APP_VERSION}"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    version = str(payload.get("version") or "").strip()
    download_url = str(payload.get("download_url") or "").strip()
    if not version or not download_url:
        return None
    return UpdateInfo(
        version=version,
        download_url=download_url,
        notes=str(payload.get("notes") or "").strip(),
        package_type=str(payload.get("package_type") or "zip").strip().lower() or "zip",
    )


def app_install_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def can_self_update():
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def can_auto_install_update(info):
    if not can_self_update():
        return False
    if not info or info.package_type != "zip":
        return False
    return info.download_url.lower().endswith(".zip")


def download_update_package(info, timeout=30):
    suffix = ".zip" if info.package_type == "zip" else ".bin"
    temp_dir = Path(tempfile.mkdtemp(prefix="medqt_update_"))
    target = temp_dir / f"medqt_update_{info.version}{suffix}"
    request = Request(info.download_url, headers={"User-Agent": f"MedQT/{APP_VERSION}"})
    with urlopen(request, timeout=timeout) as response, open(target, "wb") as output:
        while True:
            chunk = response.read(1024 * 512)
            if not chunk:
                break
            output.write(chunk)
    return target


def _windows_path(value):
    return str(value).replace("/", "\\")


def launch_windows_updater(package_path):
    package_path = Path(package_path).resolve()
    app_dir = app_install_dir().resolve()
    app_exe = Path(sys.executable).resolve()
    work_dir = package_path.parent
    extract_dir = work_dir / "expanded"
    script_path = work_dir / "apply_update.bat"
    script = f"""@echo off
setlocal
set "ZIP={_windows_path(package_path)}"
set "APPDIR={_windows_path(app_dir)}"
set "APP_EXE={_windows_path(app_exe)}"
set "EXTRACTDIR={_windows_path(extract_dir)}"

if exist "%EXTRACTDIR%" rmdir /S /Q "%EXTRACTDIR%"
mkdir "%EXTRACTDIR%"

:waitloop
tasklist /FI "IMAGENAME eq {app_exe.name}" | find /I "{app_exe.name}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACTDIR%' -Force"
robocopy "%EXTRACTDIR%" "%APPDIR%" /E /R:1 /W:1 /XF patients.db *.db data\\*.json /XD backups >nul
start "" "%APP_EXE%"
endlocal
"""
    script_path.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["cmd.exe", "/c", str(script_path)],
        cwd=str(work_dir),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def install_update(info):
    package_path = download_update_package(info)
    if info.package_type != "zip":
        raise RuntimeError("Поддерживаются только zip-обновления.")
    launch_windows_updater(package_path)
