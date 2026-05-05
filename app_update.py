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
        return Path(os.path.abspath(sys.executable)).parent
    return Path(os.path.abspath(__file__)).parent


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
    package_path = Path(os.path.abspath(package_path))
    app_dir = app_install_dir()
    app_exe = Path(os.path.abspath(sys.executable))
    work_dir = package_path.parent
    extract_dir = work_dir / "expanded"
    script_path = work_dir / "apply_update.bat"
    script = f"""@echo off
setlocal
set "ZIP={_windows_path(package_path)}"
set "APPDIR={_windows_path(app_dir)}"
set "APP_EXE={_windows_path(app_exe)}"
set "EXTRACTDIR={_windows_path(extract_dir)}"
set "LOG=%APPDIR%\\update.log"
set "ERRLOG=%APPDIR%\\update_error.log"

echo ==== MedQT updater started %date% %time% ==== > "%LOG%"
echo ZIP=%ZIP% >> "%LOG%"
echo APPDIR=%APPDIR% >> "%LOG%"
echo APP_EXE=%APP_EXE% >> "%LOG%"
echo SYS_EXECUTABLE={_windows_path(os.path.abspath(sys.executable))} >> "%LOG%"
echo SYS_ARGV0={_windows_path(os.path.abspath(sys.argv[0]))} >> "%LOG%"
echo CWD={_windows_path(os.getcwd())} >> "%LOG%"
echo FROZEN={str(bool(getattr(sys, "frozen", False))).lower()} >> "%LOG%"
if exist "%ERRLOG%" del /F /Q "%ERRLOG%"

if exist "%EXTRACTDIR%" rmdir /S /Q "%EXTRACTDIR%"
mkdir "%EXTRACTDIR%"
if errorlevel 1 (
    echo Failed to create extract dir "%EXTRACTDIR%". >> "%LOG%"
    echo Не удалось создать временную папку обновления. > "%ERRLOG%"
    echo Подробности: "%LOG%" >> "%ERRLOG%"
    exit /b 1
)

:waitloop
tasklist /FI "IMAGENAME eq {app_exe.name}" | find /I "{app_exe.name}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%EXTRACTDIR%' -Force" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo Expand-Archive failed. >> "%LOG%"
    echo Не удалось распаковать обновление. > "%ERRLOG%"
    echo Подробности: "%LOG%" >> "%ERRLOG%"
    exit /b 2
)

echo Expanded files: >> "%LOG%"
dir "%EXTRACTDIR%" /B >> "%LOG%" 2>&1

robocopy "%EXTRACTDIR%" "%APPDIR%" /E /R:1 /W:1 /XF patients.db *.db addresses.json ophthalmic_diagnoses.json comorbid_diagnoses.json treatment_basis.json examinations.json /XD backups >> "%LOG%" 2>&1
set "ROBOCOPY_EXIT=%ERRORLEVEL%"
echo Robocopy exit code=%ROBOCOPY_EXIT% >> "%LOG%"
if %ROBOCOPY_EXIT% GEQ 8 (
    echo Robocopy reported failure. >> "%LOG%"
    echo Не удалось скопировать файлы обновления. > "%ERRLOG%"
    echo Код robocopy: %ROBOCOPY_EXIT% >> "%ERRLOG%"
    echo Подробности: "%LOG%" >> "%ERRLOG%"
    exit /b %ROBOCOPY_EXIT%
)

echo App dir after copy: >> "%LOG%"
dir "%APPDIR%" /B >> "%LOG%" 2>&1
if not exist "%APP_EXE%" (
    echo Updated executable not found: "%APP_EXE%" >> "%LOG%"
    echo После обновления не найден исполняемый файл. > "%ERRLOG%"
    echo Подробности: "%LOG%" >> "%ERRLOG%"
    exit /b 3
)

echo Starting updated app... >> "%LOG%"
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
