"""WhatsApp integration: phone normalisation, templates, admin switch, send route."""
import pytest

from app.services import whatsapp_service as wa


def test_normalize_phone():
    assert wa.normalize_phone("98765 43210") == "919876543210"
    assert wa.normalize_phone("09876543210") == "919876543210"
    assert wa.normalize_phone("+1 415 555 2671") == "14155552671"
    assert wa.normalize_phone("0044 7911 123456") == "447911123456"
    assert wa.normalize_phone("9876543210", "44") == "449876543210"
    with pytest.raises(ValueError):
        wa.normalize_phone("")
    with pytest.raises(ValueError):
        wa.normalize_phone("123")


def test_render_message_defaults(db_session):
    msg = wa.render_message(
        db_session, "consultation_confirmation", patient_name="Asha", hospital_name="KT",
        context={"date": "12 Dec", "time": "10:30", "doctor_name": "Dr. Rao"},
    )
    assert "Asha" in msg and "12 10:30".split()[0] in msg and "Dr. Rao" in msg and "KT" in msg
    # missing placeholders never leak braces
    assert "{" not in wa.render_message(db_session, "lab_order_confirmation", patient_name="A")


@pytest.fixture()
def fake_sidecar(monkeypatch):
    sent = []
    monkeypatch.setattr(wa, "send", lambda phone, text, data=None, fn=None, mt=None: sent.append((phone, text, data, fn, mt)) or {"ok": True})
    monkeypatch.setattr(wa, "ensure_sidecar_running", lambda: (True, "running"))
    monkeypatch.setattr(wa, "stop_sidecar", lambda: None)
    monkeypatch.setattr(wa, "get_connection", lambda: {"state": "connected", "phone": "911111111111"})
    return sent


def test_send_blocked_until_enabled(client, auth_headers, fake_sidecar):
    r = client.put("/api/whatsapp/settings", json={"enabled": False}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = client.post("/api/whatsapp/send", data={"phone": "9876543210", "kind": "custom", "message": "hi"}, headers=auth_headers)
    assert r.status_code == 403
    assert client.get("/api/whatsapp/status", headers=auth_headers).json() == {"enabled": False, "connected": False}
    assert fake_sidecar == []


def test_enable_and_send_pdf(client, auth_headers, fake_sidecar):
    assert client.put("/api/whatsapp/settings", json={"enabled": True, "default_country_code": "91"}, headers=auth_headers).json()["enabled"] is True
    assert client.get("/api/whatsapp/status", headers=auth_headers).json() == {"enabled": True, "connected": True}
    pdf = b"%PDF-1.4 test"
    r = client.post(
        "/api/whatsapp/send",
        data={"phone": "9876543210", "kind": "pharmacy_invoice", "patient_name": "Asha"},
        files=[("files", ("inv.pdf", pdf, "application/pdf"))],
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    phone, text, data, fn, mt = fake_sidecar[-1]
    assert phone == "919876543210" and "Asha" in text and data == pdf and fn == "inv.pdf" and mt == "application/pdf"


def test_send_validation(client, auth_headers, fake_sidecar):
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    bad_pdf = client.post("/api/whatsapp/send", data={"phone": "9876543210"},
                          files=[("files", ("x.pdf", b"not pdf", "application/pdf"))], headers=auth_headers)
    assert bad_pdf.status_code == 422
    exe = client.post("/api/whatsapp/send", data={"phone": "9876543210"},
                      files=[("files", ("x.exe", b"MZ", "application/octet-stream"))], headers=auth_headers)
    assert exe.status_code == 415
    assert client.post("/api/whatsapp/send", data={"phone": "12", "message": "x"}, headers=auth_headers).status_code == 422
    assert client.post("/api/whatsapp/send", data={"phone": "9876543210", "kind": "nope"}, headers=auth_headers).status_code == 422


def test_unauthenticated(client):
    assert client.post("/api/whatsapp/send", data={"phone": "9876543210"}).status_code in (401, 403)
    assert client.put("/api/whatsapp/settings", json={"enabled": True}).status_code in (401, 403)


def test_multiple_and_zero_attachments(client, auth_headers, fake_sidecar):
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    fake_sidecar.clear()
    r = client.post(
        "/api/whatsapp/send",
        data={"phone": "9876543210", "message": "hello"},
        files=[("files", ("a.pdf", b"%PDF-1", "application/pdf")), ("files", ("b.png", b"\x89PNG", "image/png"))],
        headers=auth_headers,
    )
    assert r.status_code == 200 and r.json()["attachments"] == 2
    assert [(x[1], x[3]) for x in fake_sidecar] == [("hello", "a.pdf"), ("", "b.png")]  # caption only on first
    fake_sidecar.clear()
    assert client.post("/api/whatsapp/send", data={"phone": "9876543210", "message": "just text"}, headers=auth_headers).status_code == 200
    assert fake_sidecar == [("919876543210", "just text", None, None, None)]
    too_many = [("files", (f"{i}.pdf", b"%PDF-1", "application/pdf")) for i in range(6)]
    assert client.post("/api/whatsapp/send", data={"phone": "9876543210", "message": "x"}, files=too_many, headers=auth_headers).status_code == 422
