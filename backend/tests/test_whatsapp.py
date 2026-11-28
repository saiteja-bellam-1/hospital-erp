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
    monkeypatch.setattr(wa, "send", lambda phone, text, data=None, fn=None, mt=None, slot="primary": sent.append((phone, text, data, fn, mt)) or {"ok": True})
    monkeypatch.setattr(wa, "ensure_sidecar_running", lambda: (True, "running"))
    monkeypatch.setattr(wa, "stop_sidecar", lambda: None)
    monkeypatch.setattr(wa, "get_connection", lambda: {"state": "connected", "phone": "911111111111"})
    return sent


def test_send_blocked_until_enabled(client, auth_headers, fake_sidecar):
    r = client.put("/api/whatsapp/settings", json={"enabled": False}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = client.post("/api/whatsapp/send", data={"phone": "9876543210", "kind": "custom", "message": "hi"}, headers=auth_headers)
    assert r.status_code == 403
    assert client.get("/api/whatsapp/status", headers=auth_headers).json() == {"enabled": False, "connected": False, "connected_slots": []}
    assert fake_sidecar == []


def test_enable_and_send_pdf(client, auth_headers, fake_sidecar):
    assert client.put("/api/whatsapp/settings", json={"enabled": True, "default_country_code": "91"}, headers=auth_headers).json()["enabled"] is True
    assert client.get("/api/whatsapp/status", headers=auth_headers).json() == {"enabled": True, "connected": True, "connected_slots": ["primary"]}
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


def test_usage_counts_per_topic(client, auth_headers, fake_sidecar, monkeypatch):
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    before = client.get("/api/whatsapp/stats", headers=auth_headers).json()
    base = {r["kind"]: r for r in before["by_kind"]}

    def post(kind, files=None):
        return client.post("/api/whatsapp/send", data={"phone": "9876543210", "kind": kind, "message": "m"},
                           files=files, headers=auth_headers)

    pdf = lambda n: ("files", (n, b"%PDF-1", "application/pdf"))
    assert post("lab_report", [pdf("a.pdf")]).status_code == 200
    assert post("lab_report", [pdf("a.pdf"), pdf("b.pdf")]).status_code == 200
    assert post("prescription").status_code == 200

    def boom(*a, **k):
        raise wa.WhatsAppError("not linked")
    monkeypatch.setattr(wa, "send", boom)
    assert post("prescription").status_code == 502
    # validation rejections are not messages
    assert client.post("/api/whatsapp/send", data={"phone": "1", "kind": "lab_report", "message": "m"}, headers=auth_headers).status_code == 422

    after = client.get("/api/whatsapp/stats", headers=auth_headers).json()
    now = {r["kind"]: r for r in after["by_kind"]}
    assert now["lab_report"]["sent"] - base["lab_report"]["sent"] == 2
    assert now["lab_report"]["whatsapp_messages"] - base["lab_report"]["whatsapp_messages"] == 3
    assert now["prescription"]["sent"] - base["prescription"]["sent"] == 1
    assert now["prescription"]["failed"] - base["prescription"]["failed"] == 1
    assert now["lab_invoice"]["sent"] == base["lab_invoice"]["sent"]  # untouched topics stay put
    assert after["summary"]["today"]["sent"] >= 3 and after["summary"]["all_time"]["failed"] >= 1
    # future range -> zeros; bad range -> 422
    far = client.get("/api/whatsapp/stats", params={"date_from": "2099-01-01", "date_to": "2099-01-31"}, headers=auth_headers).json()
    assert far["sent"] == 0 and far["failed"] == 0
    assert client.get("/api/whatsapp/stats", params={"date_from": "2099-02-01", "date_to": "2099-01-01"}, headers=auth_headers).status_code == 422


# ---------------------------------------------------------------------------
# Primary / secondary failover
# ---------------------------------------------------------------------------

def _slot_sender(monkeypatch, failing=(), recipient_bad=False):
    """Fake sidecar send: slots in ``failing`` return 409 (not linked)."""
    calls = []

    def fake(phone, text, data=None, fn=None, mt=None, slot="primary"):
        calls.append(slot)
        if recipient_bad:
            raise wa.WhatsAppError("This number is not on WhatsApp", 422)
        if slot in failing:
            raise wa.WhatsAppError(f"WhatsApp {slot} number is not linked.", 409)
        return {"ok": True, "slot": slot}
    monkeypatch.setattr(wa, "send", fake)
    return calls


def test_failover_order_and_result(monkeypatch):
    calls = _slot_sender(monkeypatch)
    assert wa.send_with_failover("919876543210", "hi") == "primary"
    assert calls == ["primary"]

    calls = _slot_sender(monkeypatch, failing={"primary"})
    assert wa.send_with_failover("919876543210", "hi") == "secondary"
    assert calls == ["primary", "secondary"]

    # once a part went out on the secondary, later parts try it first
    calls = _slot_sender(monkeypatch)
    assert wa.send_with_failover("919876543210", "hi", prefer="secondary") == "secondary"
    assert calls == ["secondary"]


def test_failover_stops_on_recipient_problem(monkeypatch):
    calls = _slot_sender(monkeypatch, recipient_bad=True)
    with pytest.raises(wa.WhatsAppError):
        wa.send_with_failover("919876543210", "hi")
    assert calls == ["primary"]  # the secondary would fail the same way


def test_failover_all_down(monkeypatch):
    _slot_sender(monkeypatch, failing={"primary", "secondary"})
    with pytest.raises(wa.WhatsAppError) as exc:
        wa.send_with_failover("919876543210", "hi")
    assert "Primary" in str(exc.value) and "Secondary" in str(exc.value)


def test_send_route_uses_secondary_and_records_it(client, auth_headers, fake_sidecar, monkeypatch, db_session):
    from app.models.whatsapp import WhatsAppMessageLog
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    calls = _slot_sender(monkeypatch, failing={"primary"})
    pdf = lambda n: ("files", (n, b"%PDF-1", "application/pdf"))
    r = client.post("/api/whatsapp/send", data={"phone": "9876543210", "kind": "lab_report", "message": "m"},
                    files=[pdf("a.pdf"), pdf("b.pdf")], headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["sent_via"] == "secondary" and r.json()["failover"] is True
    # first part fails over, second goes straight to the secondary
    assert calls == ["primary", "secondary", "secondary"]
    row = db_session.query(WhatsAppMessageLog).order_by(WhatsAppMessageLog.id.desc()).first()
    assert row.sent_via == "secondary" and row.status == "sent"
    stats = client.get("/api/whatsapp/stats", headers=auth_headers).json()
    assert stats["by_number"]["secondary"] >= 1


def test_status_connected_when_only_secondary_linked(client, auth_headers, fake_sidecar, monkeypatch):
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    monkeypatch.setattr(wa, "get_connection", lambda: {
        "state": "qr", "sessions": {"primary": {"state": "qr"}, "secondary": {"state": "connected"}}})
    assert client.get("/api/whatsapp/status", headers=auth_headers).json() == {
        "enabled": True, "connected": True, "connected_slots": ["secondary"]}


def test_slot_endpoints_validate(client, auth_headers, fake_sidecar, monkeypatch):
    client.put("/api/whatsapp/settings", json={"enabled": True}, headers=auth_headers)
    seen = {}
    monkeypatch.setattr(wa, "logout", lambda slot="primary": seen.setdefault("logout", slot))
    monkeypatch.setattr(wa, "start_slot", lambda slot: seen.setdefault("start", slot) and {"slot": slot, "state": "connecting"})
    assert client.post("/api/whatsapp/logout?slot=secondary", headers=auth_headers).status_code == 200
    assert seen["logout"] == "secondary"
    assert client.post("/api/whatsapp/connection/secondary/start", headers=auth_headers).status_code == 200
    assert seen["start"] == "secondary"
    assert client.post("/api/whatsapp/logout?slot=tertiary", headers=auth_headers).status_code == 422
    assert client.post("/api/whatsapp/connection/nope/start", headers=auth_headers).status_code == 422
