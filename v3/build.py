"""Build the Windows program: a portable folder dist/MedQT/ and dist/MedQT-<version>-win.zip.

    .venv\\Scripts\\python build.py

Steps: build the interface (npm), draw the icon, bundle with PyInstaller (one folder,
no console), run `MedQT.exe --self-test` on the result, zip it. The target laptop needs
nothing installed: Windows 10/11 already has the WebView2 runtime the window uses.

The folder never contains a database: data/ is created next to MedQT.exe on first start
and is left alone by updates (copy the new folder over the old one, keep data/).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
sys.path.insert(0, str(BACKEND))
from medqt3 import __version__  # noqa: E402


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def icon(path: Path) -> None:
    """The eye in a green circle, as in the program's header: drawn large, then scaled down smoothly."""
    from PIL import Image, ImageDraw

    big = 1024
    green = (46, 107, 79, 255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([16, 16, big - 16, big - 16], fill=green)
    # The almond of the eye: two quadratic curves between the corners.
    left, right, mid, bulge = (190, 512), (834, 512), 512, 250
    pts = []
    for sign in (-1, 1):
        for i in range(101):
            t = i / 100 if sign < 0 else 1 - i / 100
            x = (1 - t) ** 2 * left[0] + 2 * (1 - t) * t * mid + t ** 2 * right[0]
            y = 512 + sign * 2 * (1 - t) * t * bulge * 1.35
            pts.append((x, y))
    d.polygon(pts, fill="white")
    d.ellipse([372, 372, 652, 652], fill=green)          # iris
    d.ellipse([452, 452, 572, 572], fill="white")        # pupil highlight ring
    d.ellipse([480, 480, 544, 544], fill=green)
    img = img.resize((256, 256), Image.LANCZOS)
    img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> None:
    step("Интерфейс (npm run build)")
    subprocess.run("npm run build", cwd=FRONTEND, shell=True, check=True)

    step("Иконка")
    BUILD.mkdir(exist_ok=True)
    ico = BUILD / "medqt.ico"
    icon(ico)

    step("PyInstaller")
    entry = BUILD / "MedQT.py"
    entry.write_text("from medqt3.desktop import main\nmain()\n", encoding="utf-8")
    sep = ";"
    args = [
        sys.executable, "-m", "PyInstaller", str(entry), "--name", "MedQT", "--noconfirm", "--clean",
        "--windowed", "--onedir", "--icon", str(ico),
        "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        "--paths", str(BACKEND),
        "--add-data", f"{FRONTEND / 'dist'}{sep}frontend",
        "--add-data", f"{BACKEND / 'medqt3' / 'fonts'}{sep}medqt3/fonts",
        "--add-data", f"{BACKEND / 'medqt3' / 'dictdata'}{sep}medqt3/dictdata",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "medqt3",
        "--collect-all", "pypdfium2",
        "--collect-all", "pypdfium2_raw",
        "--hidden-import", "win32print", "--hidden-import", "win32ui", "--hidden-import", "win32con",
    ]
    subprocess.run(args, check=True)
    app = DIST / "MedQT"

    step("Самопроверка собранной программы")
    report = BUILD / "selftest.txt"
    report.unlink(missing_ok=True)
    data = BUILD / "selftest-data"
    shutil.rmtree(data, ignore_errors=True)
    subprocess.run([str(app / "MedQT.exe"), "--self-test", str(report)], check=True, timeout=300,
                   env={**__import__("os").environ, "MEDQT_DATA": str(data)})
    text = report.read_text(encoding="utf-8")
    print(text)
    if "ЕСТЬ ОШИБКИ" in text:
        sys.exit("Самопроверка не прошла — сборка не годится.")
    if (app / "data").exists():
        sys.exit("В сборку попала папка data — её быть не должно.")

    step("Архив")
    zip_path = DIST / f"MedQT-{__version__}-win.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in app.rglob("*"):
            z.write(f, Path("MedQT") / f.relative_to(app))
    print(f"Готово: {app}\n        {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.0f} МБ)")


if __name__ == "__main__":
    main()
