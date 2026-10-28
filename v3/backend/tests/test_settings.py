import pypdfium2
from fastapi.testclient import TestClient

from medqt3 import db as store
from medqt3 import demo
from medqt3.api import create_app


def make(tmp_path):
    path = tmp_path / "t.db"
    case_id = demo.create(store.connect(path))
    return TestClient(create_app(path)), case_id


def test_defaults_follow_29(tmp_path):
    client, _ = make(tmp_path)
    s = client.get("/api/settings").json()
    assert s["doctor_signature"] == ""
    assert s["org_header"].splitlines() == ["Министерство здравоохранения", "Приднестровской Молдавской Республики", "ГУ БГЦБ"]


def test_save_trims_and_validates(tmp_path):
    client, _ = make(tmp_path)
    body = {"doctor_signature": "  Петрова Е. В. ", "org_header": " ГУ Тест \n  Отделение ", "department": "Офтальмология",
            "default_printer": ""}
    saved = client.put("/api/settings", json=body).json()
    assert saved["doctor_signature"] == "Петрова Е. В." and saved["org_header"] == "ГУ Тест\nОтделение"
    assert client.get("/api/settings").json() == saved
    assert client.put("/api/settings", json={**body, "doctor_signature": "x" * 81}).status_code == 422


def test_signature_is_printed_on_the_sheet(tmp_path):
    client, case_id = make(tmp_path)
    client.put("/api/settings", json={"doctor_signature": "Петрова Е. В.", "org_header": "", "department": "",
                                      "default_printer": ""})
    ids = [r["id"] for r in client.get(f"/api/cases/{case_id}/print-plan").json()["records"]][:3]
    job = client.post(f"/api/cases/{case_id}/print-jobs", json={"recordIds": ids, "mode": "new"}).json()
    text = pypdfium2.PdfDocument(client.get(f"/api/print-jobs/{job['jobId']}/pdf").content)[0].get_textpage().get_text_range()
    assert "Петрова Е. В." in text and "Подпись" not in text
