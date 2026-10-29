import json

import pypdfium2
import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import demo, discharge
from medqt3.api import create_app


@pytest.fixture()
def setup(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    case_id = demo.create(conn)
    return TestClient(create_app(path)), conn, case_id


def test_draft_fills_in_what_the_case_already_knows(setup):
    client, conn, case_id = setup
    d = client.get(f"/api/cases/{case_id}/discharge").json()
    form, src = d["form"], d["sources"]
    assert not d["saved"] and form["outcome"] == "улучшение"
    assert form["final_diagnosis"]                                   # the clinical diagnosis
    assert src["admissionVision"]["vis_od"]                          # Vis at admission: the primary exam
    assert src["dischargeVisionFrom"] and form["vis_od"]             # Vis at discharge: the last diary with Vis
    assert src["localFrom"] == "первичный осмотр" and form["discharge_local"]
    assert form["treatment_summary"]                                 # drug names from exam + diaries
    assert len(set(form["treatment_summary"].split(", "))) == len(form["treatment_summary"].split(", "))


def test_stay_days_count_both_ends():
    assert discharge.stay_days("2026-10-24T09:00", "2026-10-31") == 8
    assert discharge.stay_days("2026-10-31", "2026-10-31") == 1
    assert discharge.stay_days(None, "2026-10-31") is None


def test_save_discharges_then_archive_and_back(setup):
    client, conn, case_id = setup
    form = client.get(f"/api/cases/{case_id}/discharge").json()["form"]
    form.update(destination="поликлинику по месту жительства", workplace="пенсионерка",
                epicrisis="Проведено лечение.", recommendations="Наблюдение окулиста.", sig_dep_chief=True)
    r = client.put(f"/api/cases/{case_id}/discharge", json=form)
    assert r.status_code == 200
    card = client.get(f"/api/cases/{case_id}").json()
    assert card["status"] == "discharged" and card["outcome"] == "улучшение"
    assert card["diagnosis"]["final"] == form["final_diagnosis"]
    assert any(r["kind"] == "discharge_summary" for r in card["records"])
    # New diaries are not added after discharge.
    assert client.post(f"/api/cases/{case_id}/diaries", json={"date": form["discharge_date"]}).status_code == 409

    again = client.get(f"/api/cases/{case_id}/discharge").json()
    assert again["saved"] and again["form"]["destination"] == "поликлинику по месту жительства"
    assert again["form"]["sig_dep_chief"] is True
    # Saving again edits the same record.
    client.put(f"/api/cases/{case_id}/discharge", json={**form, "outcome": "без перемен"})
    assert conn.execute("SELECT COUNT(*) FROM records WHERE case_id = ? AND kind = 'discharge_summary'",
                        (case_id,)).fetchone()[0] == 1

    assert client.post(f"/api/cases/{case_id}/archive").status_code == 200
    assert case_id not in [p["caseId"] for p in client.get("/api/department").json()["patients"]]
    assert client.put(f"/api/cases/{case_id}/discharge", json=form).status_code == 409
    assert client.post(f"/api/cases/{case_id}/unarchive").status_code == 200
    assert client.get(f"/api/cases/{case_id}").json()["status"] == "discharged"

    assert client.post(f"/api/cases/{case_id}/reopen").status_code == 200
    assert client.get(f"/api/cases/{case_id}").json()["status"] == "active"
    assert client.get(f"/api/cases/{case_id}/discharge").json()["form"]["epicrisis"] == "Проведено лечение."


def test_archive_needs_a_discharge_and_dates_are_checked(setup):
    client, conn, case_id = setup
    assert client.post(f"/api/cases/{case_id}/archive").status_code == 409
    form = client.get(f"/api/cases/{case_id}/discharge").json()["form"]
    r = client.put(f"/api/cases/{case_id}/discharge", json={**form, "discharge_date": "2000-01-01"})
    assert r.status_code == 422 and "раньше" in r.json()["detail"]


def test_printed_discharge_has_the_29_items(setup):
    client, conn, case_id = setup
    assert client.get(f"/api/cases/{case_id}/discharge/pdf").status_code == 404   # nothing saved yet
    form = client.get(f"/api/cases/{case_id}/discharge").json()["form"]
    form.update(destination="поликлинику", epicrisis="Проведено лечение.", recommendations="Капли 2 недели.",
                vgd_od_max="24", elasto_od="22", tono_os_ro="18", sig_chief=True)
    client.put(f"/api/cases/{case_id}/discharge", json=form)
    r = client.get(f"/api/cases/{case_id}/discharge/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    text = "".join(p.get_textpage().get_text_range() for p in pypdfium2.PdfDocument(r.content))
    for part in ("ВЫПИСКА", "из медицинской карты стационарного больного", "1. Фамилия, имя, отчество",
                 "5. Даты", "6. Полный диагноз", "7. Эпикриз", "При поступлении", "При выписке",
                 "Тонография по Нестерову", "Эластотонометрия", "8. Лечебные и трудовые рекомендации",
                 "Главный врач", "Зав. отделением", "ГУ БГЦБ", "Находилась на стационарном лечении"):
        assert part in text, part
    assert "Зам. главного врача" not in text
    png = client.get(f"/api/cases/{case_id}/discharge/pages/1.png")
    assert png.status_code == 200 and png.headers["X-Page-Count"] == "1"


def test_29_discharge_reads_fields_kept_only_in_its_html(setup):
    client, conn, case_id = setup
    ts = store.now_iso()
    payload = {"epicrisis": "Старый эпикриз", "vis_od": "0,5", "sig_chief": True}
    html = ("<b>Куда направляется выписка:</b> в ЦРБ<br><b>Дата выписки:</b> 30.04.2026 10:00<br>"
            "<b>Место работы и род занятий:</b> учитель<br>")
    with conn:
        conn.execute("INSERT INTO records (id, case_id, kind, recorded_at, data_json, html_legacy, created_at,"
                     " updated_at, legacy_id) VALUES (?, ?, 'discharge_summary', ?, ?, ?, ?, ?, 999)",
                     (store.new_id(), case_id, "2026-04-30T10:00", json.dumps(payload, ensure_ascii=False), html, ts, ts))
        conn.execute("UPDATE cases SET status = 'discharged', discharged_at = '2026-04-30T10:00',"
                     " outcome = 'улучшение' WHERE id = ?", (case_id,))
    f = client.get(f"/api/cases/{case_id}/discharge").json()["form"]
    assert f["destination"] == "в ЦРБ" and f["workplace"] == "учитель"
    assert f["epicrisis"] == "Старый эпикриз" and f["sig_chief"] is True and f["discharge_time"] == "10:00"


def test_empty_29_field_does_not_take_the_next_line():
    plain = discharge.html_plain("<b>Куда направляется выписка:</b> <br><b>Дата выписки:</b> 17.04.2026 15:20<br>")
    assert discharge.after_label(plain, "Куда направляется выписка") == ""


def test_recommendations_from_the_last_diary_go_into_the_discharge(tmp_path):
    from fastapi.testclient import TestClient
    from medqt3 import db as store, demo
    from medqt3.api import create_app
    path = tmp_path / "t.db"
    conn = store.connect(path)
    cid = demo.create(conn)
    client = TestClient(create_app(path))
    draft = client.get(f"/api/cases/{cid}/diary-draft", params={"day": "2026-10-29"}).json()
    data = {**draft["previous"]["data"], "date": "2026-10-29", "discharge_note": "выписывается",
            "recommendations": "Тобрекс 1 кап. 4 р/д 7 дней"}
    assert client.post(f"/api/cases/{cid}/diaries", json=data).status_code in (200, 201)
    d = client.get(f"/api/cases/{cid}/discharge").json()
    assert d["form"]["recommendations"] == "Тобрекс 1 кап. 4 р/д 7 дней" and d["form"]["epicrisis"] == ""
    assert d["sources"]["diaryRecommendations"]["date"] == "2026-10-29"
