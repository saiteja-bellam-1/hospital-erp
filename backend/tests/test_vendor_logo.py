"""Vendor logo on a license, and how it sits next to hospital white-label."""

import base64
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image

from app.services.license_inspect import resolve_support_contact, seller_public_info
from app.utils.branding import resolve_branding
from app.utils.vendor_logo import decode_vendor_logo, materialize_seller


def _png_b64(width=8, height=8):
    buf = BytesIO()
    Image.new("RGB", (width, height), (20, 80, 160)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_decode_rejects_non_image():
    try:
        decode_vendor_logo(base64.b64encode(b"not-an-image").decode(), "image/png")
    except ValueError as exc:
        assert "PNG" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_materialize_writes_logo_and_clears_it(tmp_path, monkeypatch):
    monkeypatch.setattr("app.utils.paths.get_uploads_dir", lambda: str(tmp_path))
    stored = materialize_seller({
        "name": "Acme",
        "address": "1 Road",
        "phone": "999",
        "logo": _png_b64(),
        "logo_mime": "image/png",
    })
    assert stored["name"] == "Acme"
    assert "logo" not in stored
    assert stored["logo_url"].startswith("/uploads/vendor-brand/logo-")
    assert stored["logo_url"].endswith(".png")
    folder = tmp_path / "vendor-brand"
    assert len(list(folder.iterdir())) == 1

    cleared = materialize_seller({"name": "Acme", "phone": "999"})
    assert "logo_url" not in cleared
    assert list(folder.iterdir()) == []


def test_seller_public_info_drops_embedded_bytes():
    info = seller_public_info({
        "name": "Acme",
        "address": None,
        "logo": "abc",
        "logo_mime": "image/png",
    })
    assert info == {"name": "Acme", "has_logo": True}

    published = seller_public_info({
        "name": "Acme",
        "logo_url": "/uploads/vendor-brand/logo-abc.png",
        "logo": "should-not-leak",
    })
    assert published["logo_url"].endswith(".png")
    assert "logo" not in published
    assert "has_logo" not in published

    with_email = seller_public_info({"name": "Acme", "email": " a@acme.test "})
    assert with_email["email"] == "a@acme.test"


def test_resolve_support_contact_prefers_vendor_over_product_support():
    contact = resolve_support_contact(
        {"name": "Acme", "phone": "111", "email": "a@acme.test", "logo": "bytes"},
        {"name": "KT Health Soft", "phone": "222", "email": "s@kt.test"},
    )
    assert contact["name"] == "Acme"
    assert contact["email"] == "a@acme.test"
    assert contact["phone"] == "111"
    assert "logo" not in contact
    assert "has_logo" not in contact


def test_resolve_support_contact_uses_product_support_without_vendor():
    contact = resolve_support_contact(
        None,
        {"name": "KT Health Soft", "phone": "999", "email": "s@kt.test", "address": "HQ", "logo": "nope"},
    )
    assert contact == {
        "name": "KT Health Soft",
        "phone": "999",
        "email": "s@kt.test",
        "address": "HQ",
    }
    assert resolve_support_contact(None, None) is None
    assert resolve_support_contact({}, {"phone": "999"}) is None


def test_resolve_branding_keeps_hospital_and_vendor_separate():
    class Hospital:
        name = "City Hospital"
        app_logo_url = "/uploads/module-config/hospital.png"
        favicon_url = "/uploads/module-config/icon.png"
        logo_url = "/uploads/module-config/letterhead.png"

    vendor = "/uploads/vendor-brand/logo-acme.png"
    both = resolve_branding(Hospital(), customisation_licensed=True, vendor_logo_url=vendor)
    assert both["name"] == "City Hospital"
    assert both["logo_url"] == "/uploads/module-config/hospital.png"
    assert both["favicon_url"] == "/uploads/module-config/icon.png"
    assert both["vendor_logo_url"] == vendor

    waiting = resolve_branding(
        type("H", (), {"name": "City Hospital", "app_logo_url": "", "favicon_url": None})(),
        customisation_licensed=True,
        vendor_logo_url=vendor,
    )
    assert waiting["logo_url"] is None
    assert waiting["vendor_logo_url"] == vendor

    stock = resolve_branding(Hospital(), customisation_licensed=False, vendor_logo_url=vendor)
    assert stock["name"] == "KT HEALTH ERP"
    assert stock["logo_url"] is None
    assert stock["favicon_url"] is None
    assert stock["vendor_logo_url"] == vendor


def _add_license(db, *, features, seller_info, license_id):
    from app.models.license import License

    lic = License(
        license_id=license_id,
        hospital_id="TEST01",
        hospital_name="Test Hospital",
        plan="standard",
        max_users=50,
        features=features,
        seller_info=seller_info,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=30),
        status="active",
        raw_license_data="",
    )
    db.add(lic)
    db.commit()
    return lic


def test_public_branding_exposes_vendor_logo_without_customisation(client, db_session, seed_data):
    from app.models.hospital import Hospital

    hospital = db_session.query(Hospital).first()
    old_name, old_app, old_favicon = hospital.name, hospital.app_logo_url, hospital.favicon_url
    hospital.name = "Stored Custom Name"
    hospital.app_logo_url = "/uploads/module-config/stored-app.png"
    hospital.favicon_url = "/uploads/module-config/stored-icon.png"
    lic = _add_license(
        db_session,
        features=["outpatient"],
        seller_info={"name": "Acme", "logo_url": "/uploads/vendor-brand/logo-acme.png"},
        license_id="VENDOR-ONLY",
    )
    try:
        data = client.get("/api/hospital/branding/public").json()
        assert data["name"] == "KT HEALTH ERP"
        assert data["logo_url"] is None
        assert data["favicon_url"] is None
        assert data["customisation_licensed"] is False
        assert data["vendor_logo_url"] == "/uploads/vendor-brand/logo-acme.png"
    finally:
        hospital.name, hospital.app_logo_url, hospital.favicon_url = old_name, old_app, old_favicon
        db_session.delete(lic)
        db_session.commit()


def test_public_branding_hospital_logo_wins_when_both_are_set(
    client, db_session, seed_data, customisation_license,
):
    from app.models.hospital import Hospital

    hospital = db_session.query(Hospital).first()
    old_name, old_app, old_favicon = hospital.name, hospital.app_logo_url, hospital.favicon_url
    old_seller = customisation_license.seller_info
    hospital.name = "City Hospital"
    hospital.app_logo_url = "/uploads/module-config/hospital-app.png"
    hospital.favicon_url = "/uploads/module-config/icon.png"
    customisation_license.seller_info = {
        "name": "Acme",
        "address": "1 Road",
        "phone": "999",
        "logo_url": "/uploads/vendor-brand/logo-acme.png",
    }
    db_session.commit()
    try:
        data = client.get("/api/hospital/branding/public").json()
        assert data["customisation_licensed"] is True
        assert data["name"] == "City Hospital"
        assert data["logo_url"] == "/uploads/module-config/hospital-app.png"
        assert data["favicon_url"] == "/uploads/module-config/icon.png"
        assert data["vendor_logo_url"] == "/uploads/vendor-brand/logo-acme.png"
    finally:
        hospital.name, hospital.app_logo_url, hospital.favicon_url = old_name, old_app, old_favicon
        customisation_license.seller_info = old_seller
        db_session.commit()
