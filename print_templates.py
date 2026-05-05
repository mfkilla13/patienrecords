from pathlib import Path
import os
import sys


def _app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(os.path.abspath(sys.executable)).parent
    return Path(os.path.abspath(__file__)).parent


def template_path(name):
    bundled_base = Path(getattr(sys, "_MEIPASS", _app_base_dir()))
    bundled_path = bundled_base / "templates" / "print" / name
    if bundled_path.exists():
        return bundled_path
    return _app_base_dir() / "templates" / "print" / name


def render_template(name, context):
    path = template_path(name)
    text = path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace("{{ " + key + " }}", value or "")
    return text
