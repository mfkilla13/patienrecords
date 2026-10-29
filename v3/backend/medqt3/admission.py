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
            "city": p["city"], "street": p["street"], "house": p["house"],
            "lastCase": {"number": last["number"], "admittedAt": last["admitted_at"], "status": last["status"],
                         "diagnosis": last["dx_final"] or last["dx_clinical"] or last["dx_admission"]} if last else None,
        })
    return out


def admit(conn: sqlite3.Connection, a: AdmissionIn) -> dict:
    if not a.dxAdmission:
        raise AdmissionError(422, "Укажите диагноз при поступлении")
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
            conn.execute("UPDATE patients SET city = ?, street = ?, house = ?, updated_at = ? WHERE id = ?",
                         (a.city, a.street, a.house, ts, pid))
        else:
            if not a.surname:
                raise AdmissionError(422, "Фамилия обязательна")
            pid = store.new_id()
            conn.execute(
                "INSERT INTO patients (id, surname, name, patronymic, dob, city, street, house, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pid, a.surname, a.name, a.patronymic, a.dob, a.city, a.street, a.house, ts, ts))
        cid, number = store.new_id(), next_number(conn)
        admitted = f"{a.admittedDate}T{a.admittedTime}" if a.admittedTime else a.admittedDate
        conn.execute(
            "INSERT INTO cases (id, patient_id, number, med_card, admitted_at, status, dx_admission, dx_clinical,"
            " dx_comorbid, created_at, updated_at) VALUES (?,?,?,?,?,'active',?,?,?,?,?)",
            (cid, pid, number, a.medCard, admitted, a.dxAdmission, a.dxClinical, a.dxComorbid, ts, ts))
    return {"caseId": cid, "number": number, "patientId": pid}


def dictionaries(conn: sqlite3.Connection) -> dict:
    """Lists for suggestions. Towns and streets also grow from addresses already in the database."""
    addresses = dicts.get(conn, "addresses")
    cities = set(addresses["cities"])
    streets = set(addresses["streets"])
    for r in conn.execute("SELECT DISTINCT city, street FROM patients"):
        if r["city"]:
            cities.add(r["city"])
        if r["street"]:
            streets.add(r["street"])
    return {
        "ophthalmic": dicts.get(conn, "ophthalmic"),
        "comorbid": dicts.get(conn, "comorbid"),
        "examinations": dicts.get(conn, "examinations"),
        "treatment": dicts.get(conn, "treatment"),
        "cities": sorted(cities, key=str.casefold),
        "streets": sorted(streets, key=str.casefold),
        "nextNumber": next_number(conn),
    }
