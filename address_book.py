import json
import os
import sys
from pathlib import Path


DEFAULT_ADDRESSES = {
    "cities": [
        "",
        "Тирасполь",
        "Бендеры",
        "Рыбница",
        "Дубоссары",
        "Слободзея",
        "Григориополь",
        "Каменка",
        "Днестровск",
        "Парканы",
        "Гиска",
        "Суклея",
        "Косница",
        "Бутучаны",
        "Бычок",
        "Маяк",
        "Глиное",
        "Сергиевка",
        "Первомайск",
        "Солнечное",
    ],
    "streets": [
        "",
        "ул. Ленина",
        "ул. 25 Октября",
        "ул. Карла Либкнехта",
        "ул. Краснодонская",
        "ул. Комсомольская",
        "ул. Чернышевского",
        "ул. Шевченко",
        "ул. Одесская",
        "ул. Киевская",
        "ул. Транспортная",
        "ул. Советская",
        "ул. Гагарина",
        "ул. Интернациональная",
        "ул. Юности",
        "пер. Школьный",
    ],
}


def _app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundled_path():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "data" / "addresses.json"


def _user_path():
    return _app_dir() / "data" / "addresses.json"


def _unique_sorted(values):
    seen = set()
    result = []
    for value in values:
        text = (value or "").strip()
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    first = [""] if "" in result else []
    rest = sorted([v for v in result if v], key=str.casefold)
    return first + rest


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return {
            "cities": list(data.get("cities") or []),
            "streets": list(data.get("streets") or []),
        }
    except Exception:
        return {"cities": [], "streets": []}


def load_address_book():
    data = {
        "cities": list(DEFAULT_ADDRESSES["cities"]),
        "streets": list(DEFAULT_ADDRESSES["streets"]),
    }
    for path in (_bundled_path(), _user_path()):
        loaded = _read_json(path)
        data["cities"].extend(loaded["cities"])
        data["streets"].extend(loaded["streets"])
    data["cities"] = _unique_sorted(data["cities"])
    data["streets"] = _unique_sorted(data["streets"])
    return data


def get_cities():
    return load_address_book()["cities"]


def get_streets():
    return load_address_book()["streets"]


def remember_address(city="", street=""):
    data = load_address_book()
    if city:
        data["cities"].append(city.strip())
    if street:
        data["streets"].append(street.strip())
    data["cities"] = _unique_sorted(data["cities"])
    data["streets"] = _unique_sorted(data["streets"])

    path = _user_path()
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
