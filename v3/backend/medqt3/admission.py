"""New admission: find the patient (re-admissions are common — the second eye), create the case.

Case numbers continue 2.9's sequence: the next number after the largest one.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from pydantic import BaseModel, Field, field_validator

from . import db as store
from . import dicts


class AdmissionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AdmissionIn(BaseModel):
    patientId: str | None = None          # an existing patient (re-admission); otherwise a new one
    surname: str = Field("", max_length=80)
    name: str = Field("", max_length=80)
    patronymic: str = Field("", max_length=80)
    dob: str | None = None                # YYYY-MM-DD
    city: str = Field("", max_length=120)
    street: str = Field("", max_length=160)
    house: str = Field("", max_length=60)
    medCard: str = Field("", max_length=6)
    admittedDate: str
    admittedTime: str = ""
    dxAdmission: str = Field(..., max_length=500)
    dxClinical: str = Field("", max_length=500)
    dxComorbid: str = Field("", max_length=500)
    channel: str = Field("", max_length=80)           # how the patient came — for the department report
    residence: str = Field("", max_length=40)         # '' | иногородний | иностранный гражданин

    @field_validator("surname", "name", "patronymic", "city", "street", "house", "dxAdmission", "dxClinical",
                     "dxComorbid", "medCard", "admittedTime")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("medCard")
    @classmethod
    def _card(cls, v: str) -> str:
        if v and not v.isdigit():
            raise ValueError("№ мед. карты — до 6 цифр")
        return v

    @field_validator("dob", "admittedDate")
    @classmethod
    def _date(cls, v: str | None) -> str | None:
        if v:
            date.fromisoformat(v)
        return v or None

    @field_validator("admittedTime")
    @classmethod
    def _time(cls, v: str) -> str:
        if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v


def next_number(conn: sqlite3.Connection) -> str:
    numbers = [int(r[0]) for r in conn.execute("SELECT number FROM cases") if str(r[0]).isdigit()]
    return str(max(numbers, default=0) + 1)


def search(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict]:
    words = [w.casefold() for w in query.split() if w]
    if not words or len(words[0]) < 2:
        return []
    rows = conn.execute("SELECT * FROM patients WHERE deleted_at IS NULL").fetchall()
    found = []
    for p in rows:
        fio = [p["surname"].casefold(), p["name"].casefold(), p["patronymic"].casefold()]
        if all(any(part.startswith(w) for part in fio) for w in words) and fio[0].startswith(words[0]):
            found.append(p)
    found.sort(key=lambda p: (p["surname"], p["name"]))
    out = []
    for p in found[:limit]:
        last = conn.execute(
            "SELECT number, admitted_at, status, dx_final, dx_clinical, dx_admission FROM cases"
            " WHERE patient_id = ? AND deleted_at IS NULL ORDER BY admitted_at DESC LIMIT 1", (p["id"],)).fetchone()
        out.append({
            "id": p["id"], "surname": p["surname"], "name": p["name"], "patronymic": p["patronymic"], "dob": p["dob"],
            "city": p["city"], "street": p["street"], "house": p["house"], "residence": p["residence"],
            "lastCase": {"number": last["number"], "admittedAt": last["admitted_at"], "status": last["status"],
                         "diagnosis": last["dx_final"] or last["dx_clinical"] or last["dx_admission"]} if last else None,
        })
    return out


def admit(conn: sqlite3.Connection, a: AdmissionIn) -> dict:
    if not a.dxAdmission:
        raise AdmissionError(422, "Укажите диагноз при поступлении")
    from .report import CHANNELS, RESIDENCE
    if a.channel and a.channel not in CHANNELS:
        raise AdmissionError(422, "Нет такого способа госпитализации")
    if a.residence not in RESIDENCE:
        raise AdmissionError(422, "Нет такого варианта места жительства")
    if not a.patientId and a.dob and (a.dob > date.today().isoformat() or a.dob > a.admittedDate):
        raise AdmissionError(422, "Дата рождения позже даты поступления — проверьте год")
    ts = store.now_iso()
    with conn:
        if a.patientId:
            p = conn.execute("SELECT id FROM patients WHERE id = ? AND deleted_at IS NULL", (a.patientId,)).fetchone()
            if p is None:
                raise AdmissionError(404, "Пациент не найден")
            active = conn.execute("SELECT number FROM cases WHERE patient_id = ? AND status = 'active'"
                                  " AND deleted_at IS NULL", (a.patientId,)).fetchone()
            if active:
                raise AdmissionError(409, f"Пациент уже в отделении — история № {active['number']}")
            pid = a.patientId
            # The address may have changed since the last stay (2.9's wizard updated it too).
            conn.execute("UPDATE patients SET city = ?, street = ?, house = ?, residence = ?, updated_at = ? WHERE id = ?",
                         (a.city, a.street, a.house, a.residence, ts, pid))
        else:
            if not a.surname:
                raise AdmissionError(422, "Фамилия обязательна")
            pid = store.new_id()
            conn.execute(
                "INSERT INTO patients (id, surname, name, patronymic, dob, city, street, house, residence,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, a.surname, a.name, a.patronymic, a.dob, a.city, a.street, a.house, a.residence, ts, ts))
        cid, number = store.new_id(), next_number(conn)
        admitted = f"{a.admittedDate}T{a.admittedTime}" if a.admittedTime else a.admittedDate
        conn.execute(
            "INSERT INTO cases (id, patient_id, number, med_card, admitted_at, status, dx_admission, dx_clinical,"
            " dx_comorbid, admission_channel, created_at, updated_at) VALUES (?,?,?,?,?,'active',?,?,?,?,?,?)",
            (cid, pid, number, a.medCard, admitted, a.dxAdmission, a.dxClinical, a.dxComorbid, a.channel, ts, ts))
    return {"caseId": cid, "number": number, "patientId": pid}


def _ru(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def edit_form(conn: sqlite3.Connection, case_id: str) -> dict:
    """The admission data of a case as the edit form shows it (the same fields as at admission)."""
    c = conn.execute(
        "SELECT c.*, p.surname, p.name, p.patronymic, p.dob, p.city, p.street, p.house, p.residence"
        " FROM cases c JOIN patients p ON p.id = c.patient_id WHERE c.id = ? AND c.deleted_at IS NULL",
        (case_id,)).fetchone()
    if c is None:
        raise AdmissionError(404, "История не найдена")
    others = conn.execute("SELECT COUNT(*) FROM cases WHERE patient_id = ? AND id != ? AND deleted_at IS NULL",
                          (c["patient_id"], case_id)).fetchone()[0]
    admitted = c["admitted_at"] or ""
    return {
        "caseId": case_id, "number": c["number"], "status": c["status"], "dischargedAt": c["discharged_at"],
        "otherCases": others,
        "form": {
            "patientId": c["patient_id"], "surname": c["surname"], "name": c["name"], "patronymic": c["patronymic"],
            "dob": c["dob"], "city": c["city"], "street": c["street"], "house": c["house"], "medCard": c["med_card"],
            "admittedDate": admitted[:10], "admittedTime": admitted[11:16], "dxAdmission": c["dx_admission"],
            "dxClinical": c["dx_clinical"], "dxComorbid": c["dx_comorbid"], "channel": c["admission_channel"],
            "residence": c["residence"],
        },
    }


def save_edit(conn: sqlite3.Connection, case_id: str, a: AdmissionIn) -> dict:
    """Fix what was typed at admission. The patient's own data (name, date of birth, address) is the same
    in all their stays, so it changes there too; the stay's data changes only in this case."""
    from .report import CHANNELS, RESIDENCE
    c = conn.execute("SELECT * FROM cases WHERE id = ? AND deleted_at IS NULL", (case_id,)).fetchone()
    if c is None:
        raise AdmissionError(404, "История не найдена")
    today = date.today().isoformat()
    if not a.surname:
        raise AdmissionError(422, "Фамилия обязательна")
    if not a.dxAdmission:
        raise AdmissionError(422, "Укажите диагноз при поступлении")
    if a.admittedDate > today:
        raise AdmissionError(422, "Дата поступления не может быть позже сегодняшней")
    if a.dob and (a.dob > today or a.dob > a.admittedDate):
        raise AdmissionError(422, "Дата рождения позже даты поступления — проверьте год")
    if c["discharged_at"] and a.admittedDate > c["discharged_at"][:10]:
        raise AdmissionError(422, f"Дата поступления позже даты выписки ({_ru(c['discharged_at'])})")
    first = conn.execute("SELECT MIN(substr(recorded_at, 1, 10)) FROM records WHERE case_id = ? AND deleted_at IS NULL"
                         " AND kind NOT IN ('passport', 'discharge_summary')", (case_id,)).fetchone()[0]
    # Only when the date is moved: an old 2.9 stay with such a record can still have its other fields fixed.
    if first and a.admittedDate > first and a.admittedDate != (c["admitted_at"] or "")[:10]:
        raise AdmissionError(422, f"В истории есть записи раньше этой даты (от {_ru(first)}) — поступление не может быть позже")
    if a.channel and a.channel not in CHANNELS:
        raise AdmissionError(422, "Нет такого способа госпитализации")
    if a.residence not in RESIDENCE:
        raise AdmissionError(422, "Нет такого варианта места жительства")
    ts = store.now_iso()
    admitted = f"{a.admittedDate}T{a.admittedTime}" if a.admittedTime else a.admittedDate
    with conn:
        conn.execute("UPDATE patients SET surname = ?, name = ?, patronymic = ?, dob = ?, city = ?, street = ?, house = ?,"
                     " residence = ?, updated_at = ? WHERE id = ?",
                     (a.surname, a.name, a.patronymic, a.dob, a.city, a.street, a.house, a.residence, ts, c["patient_id"]))
        conn.execute("UPDATE cases SET med_card = ?, admitted_at = ?, dx_admission = ?, dx_clinical = ?, dx_comorbid = ?,"
                     " admission_channel = ?, updated_at = ? WHERE id = ?",
                     (a.medCard, admitted, a.dxAdmission, a.dxClinical, a.dxComorbid, a.channel, ts, case_id))
    return {"caseId": case_id}


def dictionaries(conn: sqlite3.Connection) -> dict:
    """Lists for suggestions. Towns and streets also grow from addresses already in the database.

    Settlements keep the dictionary's order — the towns (Бендеры, Тирасполь, ...) first, then the
    villages; the doctor can reorder them in Справочники → Адреса. Ones that are only in the database
    follow at the end."""
    from .report import CHANNELS, RESIDENCE
    addresses = dicts.get(conn, "addresses")
    known = {c.casefold() for c in addresses["cities"]}
    extra_cities, streets = set(), set(addresses["streets"])
    for r in conn.execute("SELECT DISTINCT city, street FROM patients WHERE deleted_at IS NULL"):
        if r["city"] and r["city"].casefold() not in known:
            extra_cities.add(r["city"])
        if r["street"]:
            streets.add(r["street"])
    cities = addresses["cities"] + sorted(extra_cities, key=str.casefold)
    return {
        "ophthalmic": dicts.get(conn, "ophthalmic"),
        "comorbid": dicts.get(conn, "comorbid"),
        "examinations": dicts.get(conn, "examinations"),
        "treatment": dicts.get(conn, "treatment"),
        "cities": cities,
        "streets": sorted(streets, key=str.casefold),
        "nextNumber": next_number(conn),
        "channels": list(CHANNELS),
        "residence": RESIDENCE,
    }
