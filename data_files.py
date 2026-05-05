import json
import os
import sys
from pathlib import Path


def app_dir():
    if getattr(sys, "frozen", False):
        return Path(os.path.abspath(sys.executable)).parent
    return Path(os.path.abspath(__file__)).parent


def bundled_data_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(os.path.abspath(__file__)).parent))
    return base / "data"


def user_data_dir():
    return app_dir() / "data"


def bundled_data_path(file_name):
    return bundled_data_dir() / file_name


def user_data_path(file_name):
    return user_data_dir() / file_name


def ensure_user_data_dir():
    user_data_dir().mkdir(parents=True, exist_ok=True)


def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data
    except Exception:
        return default


def load_data_json(file_name, default):
    bundled = load_json_file(bundled_data_path(file_name), default)
    user = load_json_file(user_data_path(file_name), default)

    if isinstance(default, list):
        result = []
        for source in (bundled, user):
            if isinstance(source, list):
                result.extend(source)
        seen = set()
        unique = []
        for item in result:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    if isinstance(default, dict):
        result = {}
        if isinstance(bundled, dict):
            result.update(bundled)
        if isinstance(user, dict):
            for key, value in user.items():
                if isinstance(value, list) and isinstance(result.get(key), list):
                    merged = list(result[key])
                    for item in value:
                        if item not in merged:
                            merged.append(item)
                    result[key] = merged
                else:
                    result[key] = value
        return result

    return user if user != default else bundled
