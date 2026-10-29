import sys
import time

import pypdfium2
import pytest
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import printjobs, printlayout

TOP = printlayout.CONTENT_TOP_MM   # where records start on a fresh sheet (under the heading)
from medqt3.api import create_app


def diary(day, **kw):
    d = {"date": day, "time": "09:00", "bp": "130/80", "vis_od": "0,6", "vis_os": "0,5", "vgd_od": "18",
         "vgd_os": "19", "complaints": "нет", "od_text": "роговица прозрачная", "treatment": "продолжить"}
    d.update(kw)
    return d


@pytest.fixture()
def env(tmp_path):
    path = tmp_path / "t.db"
    conn = store.connect(path)
    ts = store.now_iso()
    with conn:
        conn.execute("INSERT INTO patients (id, surname, name, created_at, updated_at) VALUES ('p1', 'Тестова', 'Анна', ?, ?)", (ts, ts))
        conn.execute("INSERT INTO cases (id, patient_id, number, admitted_at, status, created_at, updated_at)"
                     " VALUES ('c1', 'p1', '1', '2026-10-01T09:00', 'active', ?, ?)", (ts, ts))
    conn.close()
    client = TestClient(create_app(path))
    ids = [client.post("/api/cases/c1/diaries", json=diary(f"2026-10-{d:02d}")).json()["id"] for d in (20, 21, 22)]
    return client, ids, path


def job(client, ids, **kw):
    r = client.post("/api/cases/c1/print-jobs", json={"recordIds": ids, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def print_and_confirm(client, ids, **kw):
    j = job(client, ids, **kw)
    assert client.post(f"/api/print-jobs/{j['jobId']}/confirm").status_code == 200
    return j


def ink_rows_mm(pdf: bytes, page: int = 0) -> list[float]:
    """Millimetres (from the top edge) of every pixel row that has ink."""
    pg = pypdfium2.PdfDocument(pdf)[page]
    dpi = 150
    img = pg.render(scale=dpi / 72, grayscale=True).to_pil()
    px = img.load()
    return [y / dpi * 25.4 for y in range(img.height) if any(px[x, y] < 128 for x in range(0, img.width, 3))]


def place(client, rid):
    return next(r["place"] for r in client.get("/api/cases/c1/print-plan").json()["records"] if r["id"] == rid)


def test_first_print_starts_new_sheet_and_confirm_stores_places(env):
    client, ids, _ = env
    plan = client.get("/api/cases/c1/print-plan").json()
    assert plan["suggestion"] == {"mode": "new", "sheet": 1, "startMm": TOP}

    j = job(client, ids[:2], mode="new")
    assert j["newStart"] == {"sheet": 1, "mm": TOP} and [p["sheet"] for p in j["pages"]] == [1]
    assert j["pages"][0]["insert"].startswith("чистый лист")
    # Nothing is marked before the doctor confirms.
    assert all(r["printedAt"] is None for r in client.get("/api/cases/c1/print-plan").json()["records"])

    client.post(f"/api/print-jobs/{j['jobId']}/confirm")
    plan = client.get("/api/cases/c1/print-plan").json()
    assert [bool(r["printedAt"]) for r in plan["records"]] == [True, True, False]
    assert plan["records"][0]["place"] == {"sheet": 1, "startMm": TOP}
    assert plan["records"][1]["place"]["startMm"] > TOP
    assert plan["suggestion"]["mode"] == "continue" and plan["lastOnSheet"] == "21.10"


def test_continue_starts_right_below_previous_print(env):
    client, ids, _ = env
    first = print_and_confirm(client, ids[:2], mode="new")
    nxt = job(client, ids[2:], mode="continue")
    assert nxt["newStart"]["sheet"] == 1
    assert nxt["newStart"]["mm"] == pytest.approx(first["newEnd"]["mm"] + printlayout.GAP_MM, abs=0.1)
    assert nxt["pages"][0]["insert"] == "лист 1 (на нём записи до 21.10)"
    pdf = client.get(f"/api/print-jobs/{nxt['jobId']}/pdf").content
    assert nxt["newStart"]["mm"] <= ink_rows_mm(pdf)[0] <= nxt["newStart"]["mm"] + 3


def test_continue_below_a_handwritten_note(env):
    """Another doctor wrote by hand under our last print: the next print starts below the handwriting."""
    client, ids, _ = env
    first = print_and_confirm(client, ids[:1], mode="new")
    end = first["newEnd"]["mm"]
    j = job(client, ids[1:2], mode="continue", handwrittenTo=150)
    assert j["newStart"] == {"sheet": 1, "mm": pytest.approx(150 + printlayout.GAP_MM, abs=0.1)}
    assert [round(end, 1), 150.0] in j["pages"][0]["shade"]          # shown as already on paper
    rows = ink_rows_mm(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)
    assert rows[0] >= 150                                             # nothing printed over the handwriting
    client.post(f"/api/print-jobs/{j['jobId']}/cancel")

    bad = client.post("/api/cases/c1/print-jobs", json={"recordIds": ids[1:2], "mode": "continue", "handwrittenTo": end - 10})
    assert bad.status_code == 422
    near_bottom = job(client, ids[1:2], mode="continue", handwrittenTo=270)   # no room left under it
    assert near_bottom["movedToNewSheet"] is True and near_bottom["newStart"]["sheet"] == 2


def test_handwriting_running_over_to_the_next_sheet(env):
    """The handwritten note started under our print on sheet 1 and ended on sheet 2 at 60 mm."""
    client, ids, _ = env
    print_and_confirm(client, ids[:1], mode="new")
    j = job(client, ids[1:2], mode="continue", handwrittenTo=60, handwrittenSheet=2)
    assert j["newStart"] == {"sheet": 2, "mm": pytest.approx(60 + printlayout.GAP_MM, abs=0.1)}
    page = j["pages"][0]
    assert page["sheet"] == 2 and page["fresh"] is False                 # no heading over the handwriting
    assert page["insert"] == "лист 2 (на нём запись от руки до 60 мм)"
    assert page["shade"] == [[printlayout.SHEET_TOP_MM, 60.0]]
    text = pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)[0].get_textpage().get_text_range()
    assert "Офтальмологическое отделение" not in text and "21.10.2026" in text
    assert ink_rows_mm(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)[0] >= 60
    client.post(f"/api/print-jobs/{j['jobId']}/confirm")
    plan = client.get("/api/cases/c1/print-plan").json()
    assert plan["state"]["sheet"] == 2                                   # the next print continues sheet 2

    too_far = client.post("/api/cases/c1/print-jobs", json={"recordIds": ids[2:], "mode": "continue",
                                                            "handwrittenTo": 50, "handwrittenSheet": 5})
    assert too_far.status_code == 422


def test_sheet_heading_only_when_a_sheet_starts(env):
    client, ids, _ = env
    text = lambda j, page=0: pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)[page].get_textpage().get_text_range()  # noqa: E731
    first = print_and_confirm(client, ids[:1], mode="new")
    t = text(first)
    assert "Офтальмологическое отделение" in t and "Тестова Анна" in t and "лист 1" in t
    assert first["pages"][0]["fresh"] is True
    more = job(client, ids[1:2], mode="continue")             # continuing the same sheet: no heading again
    t = text(more)
    assert "Офтальмологическое отделение" not in t and "лист 1" not in t and "20.10" not in t and "21.10.2026" in t
    assert more["pages"][0]["fresh"] is False


def test_reprint_goes_to_its_own_place_and_new_record_below_the_last(env):
    """The case from the doctor: tick an old record (20.10) and a new one (22.10) together."""
    client, ids, _ = env
    print_and_confirm(client, ids[:2], mode="new")           # 20.10 and 21.10 are on sheet 1
    p20, p21 = place(client, ids[0]), place(client, ids[1])
    j = job(client, [ids[0], ids[2]], mode="continue")
    assert j["reprintCount"] == 1 and j["newCount"] == 1 and len(j["pages"]) == 1
    rows = ink_rows_mm(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)
    assert p20["startMm"] <= rows[0] <= p20["startMm"] + 3   # 20.10 reprinted exactly over itself
    assert not [y for y in rows if p21["startMm"] + 1 < y < j["newStart"]["mm"] - 1]  # 21.10's place is left alone
    assert j["newStart"]["mm"] > p21["startMm"]               # 22.10 goes below 21.10, not after 20.10

    # 21.10 is shaded as "already on paper"; 20.10 (being reprinted) is not hidden under the shading.
    (top, bottom), = j["pages"][0]["shade"]
    assert top == pytest.approx(p21["startMm"], abs=0.1) and bottom < j["newStart"]["mm"]

    client.post(f"/api/print-jobs/{j['jobId']}/confirm")
    assert place(client, ids[0]) == p20                      # reprint does not move the old record
    assert place(client, ids[2])["startMm"] == pytest.approx(j["newStart"]["mm"], abs=0.1)


def test_reprinting_the_only_record_on_a_sheet_shades_nothing(env):
    client, ids, _ = env
    print_and_confirm(client, ids[:1], mode="new")
    j = job(client, [ids[0], ids[1]], mode="continue")   # reprint 20.10 + new 21.10 below it
    assert j["pages"][0]["shade"] == []


def test_fixed_render_matches_measured_places(env):
    client, ids, _ = env
    print_and_confirm(client, ids, mode="new")
    for rid in ids:
        p = place(client, rid)
        j = job(client, [rid], mode="continue")
        rows = ink_rows_mm(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)
        assert p["startMm"] <= rows[0] <= p["startMm"] + 3
        client.post(f"/api/print-jobs/{j['jobId']}/cancel")


def test_record_printed_by_29_cannot_be_put_in_place_but_can_be_copied(env):
    client, ids, path = env
    conn = store.connect(path)
    with conn:  # printed by 2.9: marked, but its place on the sheet is unknown
        conn.execute("UPDATE records SET printed_at = '2026-10-20T12:00' WHERE id = ?", (ids[0],))
    r = client.post("/api/cases/c1/print-jobs", json={"recordIds": [ids[0]], "mode": "new"})
    assert r.status_code == 422 and "2.9" in r.json()["detail"]
    copy = job(client, [ids[0], ids[1]], kind="copy", mode="new")
    assert copy["newCount"] == 0 and copy["pages"][0]["insert"] == "чистый лист"
    client.post(f"/api/print-jobs/{copy['jobId']}/confirm")
    plan = client.get("/api/cases/c1/print-plan").json()
    assert plan["state"] is None and plan["records"][1]["printedAt"] is None   # a copy marks nothing


def test_cancel_changes_nothing(env):
    client, ids, _ = env
    j = job(client, ids, mode="new")
    client.post(f"/api/print-jobs/{j['jobId']}/cancel")
    plan = client.get("/api/cases/c1/print-plan").json()
    assert plan["state"] is None and all(r["printedAt"] is None and r["place"] is None for r in plan["records"])
    assert client.post(f"/api/print-jobs/{j['jobId']}/confirm").status_code == 409


def test_not_enough_room_moves_to_next_sheet(env):
    client, ids, _ = env
    j = job(client, ids, mode="manual", startMm=260)
    assert j["movedToNewSheet"] is True and j["newStart"] == {"sheet": 2, "mm": TOP}


def test_manual_offset_is_validated_and_used(env):
    client, ids, _ = env
    assert client.post("/api/cases/c1/print-jobs", json={"recordIds": ids, "mode": "manual", "startMm": 2}).status_code == 422
    j = job(client, ids[:1], mode="manual", startMm=118)
    assert 118 <= ink_rows_mm(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)[0] <= 121
    assert j["pages"][0]["shade"] == [[printlayout.SHEET_TOP_MM, 116.5]]   # unknown content above the offset is shaded
    assert client.get(f"/api/print-jobs/{j['jobId']}/pages/1.png").headers["content-type"] == "image/png"


def test_continue_without_v3_history_is_refused(env):
    client, ids, path = env
    conn = store.connect(path)
    with conn:  # a position carried over from 2.9 means something else and is never trusted
        conn.execute("INSERT INTO print_state (case_id, used_mm, source, updated_at) VALUES ('c1', 80, 'legacy', 'x')")
    assert client.get("/api/cases/c1/print-plan").json()["suggestion"]["mode"] == "new"
    assert client.post("/api/cases/c1/print-jobs", json={"recordIds": ids, "mode": "continue"}).status_code == 409


def test_parallel_page_previews_of_a_two_sheet_job(env):
    """The browser loads all page images at once; pdfium must not be hit from two threads."""
    from concurrent.futures import ThreadPoolExecutor
    client, _, _ = env
    ids = [client.post("/api/cases/c1/diaries", json=diary(f"2026-10-{d:02d}", od_text="длинный текст " * 40)).json()["id"]
           for d in range(1, 12)]
    j = job(client, ids, mode="new")
    assert len(j["pages"]) >= 2
    urls = [f"/api/print-jobs/{j['jobId']}/pages/{p}.png" for p in range(1, len(j["pages"]) + 1)] * 4
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(lambda u: client.get(u).status_code, urls))
    assert statuses == [200] * len(urls)


LEGACY_EXAM_HTML = """
<style>.title{ font-weight:700; } body{ font-size: 10.5pt; }</style>
<div class="section"><span class="title">Жалобы:</span> на снижение зрения</div>
<b>Офтальмологический осмотр:</b><br>
<table border="0" cellpadding="0" cellspacing="0"><tr>
  <td style="padding:0 5px;"><b>Vis</b></td>
  <td style="padding:0 5px;"><table border="0" cellpadding="2" cellspacing="0">
    <tr><td style="border-bottom:1px solid black;">OD</td></tr><tr><td>OS</td></tr></table></td>
  <td>=</td>
  <td><table border="0" cellpadding="2" cellspacing="0">
    <tr><td style="border-bottom:1px solid black;">0,3</td></tr><tr><td>0,6</td></tr></table></td>
</tr></table>
<table border="1"><tr><th>Позиция</th><th>OD</th><th>OS</th></tr>
<tr><td>Хрусталик</td><td>неравномерно мутный</td><td>прозрачный</td></tr></table>
"""


def test_primary_exam_from_29_prints_from_its_saved_text(env):
    client, ids, path = env
    conn = store.connect(path)
    with conn:  # a 2.9 exam: no fields, only the HTML it was printed from
        conn.execute("INSERT INTO records (id, case_id, kind, recorded_at, html_legacy, created_at, updated_at)"
                     " VALUES ('ex', 'c1', 'primary_exam', '2026-10-19T11:46:00', ?, 'x', 'x')", (LEGACY_EXAM_HTML,))
    plan = client.get("/api/cases/c1/print-plan").json()
    exam = plan["records"][0]
    assert exam["id"] == "ex" and exam["printable"] is True     # comes first: it is the earliest record
    j = job(client, ["ex", ids[0]], mode="new")
    text = pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{j['jobId']}/pdf").content)[0].get_textpage().get_text_range()
    for expected in ("19.10.2026", "11:46", "Первичный осмотр", "Жалобы:", "на снижение зрения",
                     "0,3", "0,6", "Хрусталик", "неравномерно мутный", "Подпись", "20.10.2026"):
        assert expected in text, expected
    assert text.index("Первичный осмотр") < text.index("20.10.2026")   # exam before the next day's diary


def test_legacy_diary_date_format_prints(env):
    client, ids, path = env
    conn = store.connect(path)
    with conn:  # 2.9 kept "30.04.2026" inside the diary JSON
        conn.execute("UPDATE records SET data_json = json_set(data_json, '$.date', '30.04.2026') WHERE id = ?", (ids[0],))
    j = job(client, ids[:1], mode="new")
    pdf = client.get(f"/api/print-jobs/{j['jobId']}/pdf").content
    assert "30.04.2026" in pypdfium2.PdfDocument(pdf)[0].get_textpage().get_text_range()
    assert client.get(f"/api/diaries/{ids[0]}").json()["data"]["date"] == "2026-04-30"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows printing")
def test_windows_print_keeps_exact_position(env, tmp_path):
    from medqt3 import winprint
    if "Microsoft Print to PDF" not in winprint.printers()["printers"]:
        pytest.skip("no Microsoft Print to PDF")
    client, ids, path = env
    j = job(client, ids[:1], mode="manual", startMm=118)
    original = client.get(f"/api/print-jobs/{j['jobId']}/pdf").content
    out = tmp_path / "printed.pdf"
    printjobs.send_to_printer(store.connect(path), j["jobId"], "Microsoft Print to PDF", str(out))
    for _ in range(40):
        if out.exists() and out.stat().st_size:
            break
        time.sleep(0.25)
    assert abs(ink_rows_mm(out.read_bytes())[0] - ink_rows_mm(original)[0]) < 0.3


def test_sheets_carry_the_paper_case_number_not_the_programs(tmp_path):
    from medqt3 import db as store, demo, printjobs, printlayout
    conn = store.connect(tmp_path / "t.db")
    cid = demo.create(conn)
    with conn:
        conn.execute("UPDATE cases SET number = '310', med_card = '4521' WHERE id = ?", (cid,))
    info = printjobs._sheet_info(conn, cid)
    assert info.number == "4521" and "№ 4521" in info.short
    with conn:
        conn.execute("UPDATE cases SET med_card = '' WHERE id = ?", (cid,))
    assert printjobs._sheet_info(conn, cid).number == printlayout.paper_number("") == "________"
