"""WhatsApp license gate, phone normalization, MSG91 payload, and media links."""

import time
from datetime import datetime, timedelta

import pytest

from app.services.whatsapp.phone import InvalidPhone, normalize_phone
from app.services.whatsapp.registry import (
    DocumentKind,
    PreparedDocument,
    register_document_kind,
    unregister_document_kind,
)
from app.services.whatsapp.settings import WhatsAppNotReady, validate_public_base_url


def test_normalize_phone_adds_india_code():
    assert normalize_phone("98765 43210") == "919876543210"
    assert normalize_phone("09876543210") == "919876543210"
    assert normalize_phone("+1 415 555 0123") == "14155550123"


def test_normalize_phone_rejects_short_numbers():
    with pytest.raises(InvalidPhone):
        normalize_phone("12345")


def test_public_base_url_rejects_a_path():
    assert validate_public_base_url("https://hospital.example/") == "https://hospital.example"
    with pytest.raises(WhatsAppNotReady):
        validate_public_base_url("https://hospital.example/erp")


def test_enabled_modules_hides_whatsapp_without_license(client, auth_headers, seed_data):
    res = client.get("/api/system/enabled-modules", headers=auth_headers)
    assert res.status_code == 200
    by_name = {row["module_name"]: row["is_enabled"] for row in res.json()}
    assert by_name.get("whatsapp") is False


def test_send_requires_the_license(client, auth_headers, seed_data):
    res = client.post(
        "/api/whatsapp/documents",
        headers=auth_headers,
        json={"kind": "hospital_bill", "resource_id": "1", "phone": "9876543210"},
    )
    assert res.status_code == 403


def _grant_whatsapp(db_session):
    from app.models.license import License
    from app.services.license_service import FEATURE_WHATSAPP

    existing = db_session.query(License).order_by(License.id.desc()).first()
    if existing:
        old = list(existing.features or [])
        if FEATURE_WHATSAPP not in old:
            existing.features = old + [FEATURE_WHATSAPP]
            db_session.commit()
        return existing, old
    lic = License(
        license_id="TEST-WHATSAPP",
        hospital_id="TEST01",
        hospital_name="Test Hospital",
        plan="standard",
        max_users=100,
        features=[FEATURE_WHATSAPP],
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        status="active",
        raw_license_data="",
    )
    db_session.add(lic)
    db_session.commit()
    return lic, None


def _save_ready_settings(client, auth_headers, **overrides):
    payload = {
        "enabled": True,
        "auth_key": "secret-key",
        "integrated_number": "919800000000",
        "public_base_url": "https://hospital.example",
        "template_invoice": "kt_invoice",
    }
    payload.update(overrides)
    return client.put("/api/whatsapp/settings", headers=auth_headers, json=payload)


def test_local_switch_off_rejects_send(client, auth_headers, db_session, seed_data):
    license_row, old_features = _grant_whatsapp(db_session)
    register_document_kind(DocumentKind(
        key="test_invoice_off",
        template_family="invoice",
        load=lambda db, user, resource_id, include_header=None: PreparedDocument(
            pdf_bytes=b"%PDF",
            filename="INV.pdf",
            phone="",
            patient_name="Ada",
            reference="INV",
            document_date="2026-10-10",
            resource_type="Bill",
            resource_id=resource_id,
            template_family="invoice",
        ),
    ))
    try:
        saved = _save_ready_settings(client, auth_headers, enabled=False)
        assert saved.status_code == 200, saved.text
        sent = client.post(
            "/api/whatsapp/documents",
            headers=auth_headers,
            json={"kind": "test_invoice_off", "resource_id": "1", "phone": "9876543210"},
        )
        assert sent.status_code == 403
        assert "turned off" in sent.json()["detail"]
    finally:
        unregister_document_kind("test_invoice_off")
        if old_features is not None:
            license_row.features = old_features
            db_session.commit()
        else:
            db_session.delete(license_row)
            db_session.commit()


def test_missing_auth_key_is_a_clear_400(client, auth_headers, db_session, seed_data):
    from app.models.permissions import HospitalSettings

    license_row, old_features = _grant_whatsapp(db_session)
    db_session.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "whatsapp",
        HospitalSettings.setting_key == "auth_key",
    ).delete()
    db_session.commit()
    register_document_kind(DocumentKind(
        key="test_invoice_nokey",
        template_family="invoice",
        load=lambda db, user, resource_id, include_header=None: PreparedDocument(
            pdf_bytes=b"%PDF",
            filename="INV.pdf",
            phone="",
            patient_name="Ada",
            reference="INV",
            document_date="2026-10-10",
            resource_type="Bill",
            resource_id=resource_id,
            template_family="invoice",
        ),
    ))
    try:
        saved = _save_ready_settings(client, auth_headers, auth_key="")
        assert saved.status_code == 200, saved.text
        sent = client.post(
            "/api/whatsapp/documents",
            headers=auth_headers,
            json={"kind": "test_invoice_nokey", "resource_id": "1", "phone": "9876543210"},
        )
        assert sent.status_code == 400
        assert "auth key" in sent.json()["detail"].lower()
    finally:
        unregister_document_kind("test_invoice_nokey")
        if old_features is not None:
            license_row.features = old_features
            db_session.commit()
        else:
            db_session.delete(license_row)
            db_session.commit()


def test_send_posts_a_document_template(client, auth_headers, db_session, seed_data, monkeypatch, tmp_path):
    from app.services.whatsapp import media as media_store
    from app.services.whatsapp import msg91

    license_row, old_features = _grant_whatsapp(db_session)
    monkeypatch.setattr(media_store, "_media_dir", lambda: str(tmp_path))
    media_store.clear_all()

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers

        class Response:
            status_code = 200
            text = ""

            def json(self):
                return {"request_id": "req-1"}

        return Response()

    monkeypatch.setattr(msg91.requests, "post", fake_post)

    def load(db, user, resource_id, include_header=None):
        return PreparedDocument(
            pdf_bytes=b"%PDF-1.4 test",
            filename="INV-1.pdf",
            phone="9876543210",
            patient_name="Ada",
            reference="INV-1",
            document_date="2026-10-10",
            resource_type="Bill",
            resource_id=resource_id,
            template_family="invoice",
        )

    register_document_kind(DocumentKind(key="test_invoice", template_family="invoice", load=load))
    try:
        saved = client.put(
            "/api/whatsapp/settings",
            headers=auth_headers,
            json={
                "enabled": True,
                "auth_key": "secret-key",
                "integrated_number": "919800000000",
                "public_base_url": "https://hospital.example",
                "template_invoice": "kt_invoice",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["auth_key_set"] is True
        assert "auth_key" not in saved.json()

        sent = client.post(
            "/api/whatsapp/documents",
            headers=auth_headers,
            json={"kind": "test_invoice", "resource_id": "9", "phone": "9876543210"},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "submitted"
        assert sent.json()["phone"] == "919876543210"

        template = captured["json"]["payload"]["template"]
        assert template["name"] == "kt_invoice"
        header = template["to_and_components"][0]["components"]["header_1"]
        assert header["type"] == "document"
        assert header["filename"] == "INV-1.pdf"
        assert header["value"].startswith("https://hospital.example/api/whatsapp/media/")
        assert captured["headers"]["authkey"] == "secret-key"
        assert "secret-key" not in sent.text

        token = header["value"].rsplit("/", 1)[-1]
        fetched = client.get(f"/api/whatsapp/media/{token}")
        assert fetched.status_code == 200
        assert fetched.content.startswith(b"%PDF")

        media_store._tokens[token] = (media_store._tokens[token][0], time.time() - 1)
        assert client.get(f"/api/whatsapp/media/{token}").status_code == 404
    finally:
        unregister_document_kind("test_invoice")
        media_store.clear_all()
        if old_features is not None:
            license_row.features = old_features
            db_session.commit()
        else:
            db_session.delete(license_row)
            db_session.commit()
