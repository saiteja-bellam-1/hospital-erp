"""Item creation rules: company required, code from name, doctor on scheduled sales."""

import uuid
from datetime import date

from app.models.pharmacy import PharmacyCompany


def _company(db_session, hospital_id):
    co = PharmacyCompany(name=f"Co-{uuid.uuid4().hex[:6]}", hospital_id=hospital_id, is_active=True)
    db_session.add(co)
    db_session.commit()
    return co


def test_medicine_requires_company_not_category(client, auth_headers, db_session, seed_data):
    co = _company(db_session, seed_data["hospital_id"])
    missing = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={"name": "No Company", "rate_a": 10},
    )
    assert missing.status_code == 422, missing.text

    created = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={"name": "Crocin Advance", "company_id": co.id, "rate_a": 12},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category_id"] is None
    assert body["company_id"] == co.id
    assert body["medicine_code"] == "CROCINADVANCE"


def test_duplicate_name_code_gets_suffix(client, auth_headers, db_session, seed_data):
    co = _company(db_session, seed_data["hospital_id"])
    first = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={"name": "Dolo 650", "company_id": co.id, "rate_a": 10},
    )
    assert first.status_code == 201, first.text
    assert first.json()["medicine_code"] == "DOLO650"

    second = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={"name": "Dolo 650", "company_id": co.id, "medicine_code": "DOLO650", "rate_a": 10},
    )
    assert second.status_code == 201, second.text
    assert second.json()["medicine_code"] == "DOLO6502"

    manual = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={"name": "Something Else", "company_id": co.id, "medicine_code": "DOLO650", "rate_a": 10},
    )
    assert manual.status_code == 400
    assert "already exists" in manual.json()["detail"].lower()


def test_scheduled_sale_requires_doctor_name(client, auth_headers, db_session, seed_data):
    hid = seed_data["hospital_id"]
    co = _company(db_session, hid)
    today = date.today().isoformat()

    sup = client.post(
        "/api/pharmacy/suppliers",
        headers=auth_headers,
        json={"name": f"Sch Sup {uuid.uuid4().hex[:4]}", "is_active": True},
    )
    assert sup.status_code == 201, sup.text

    med = client.post(
        "/api/pharmacy/medicines",
        headers=auth_headers,
        json={
            "name": "Schedule H Tablet",
            "company_id": co.id,
            "rate_a": 20,
            "mrp": 20,
            "is_schedule_h": True,
        },
    )
    assert med.status_code == 201, med.text
    mid = med.json()["id"]

    draft = client.post(
        "/api/pharmacy/purchases",
        headers=auth_headers,
        json={
            "entry_date": today,
            "supplier_id": sup.json()["id"],
            "invoice_number": f"SCH-{uuid.uuid4().hex[:6]}",
            "payment_type": "cash",
            "purchase_type": "local",
            "items": [{
                "medicine_id": mid,
                "batch_number": "SCH-B1",
                "expiry_date": "2028-12-31",
                "mrp": 20,
                "quantity": 10,
                "free_quantity": 0,
                "purchase_rate": 10,
            }],
        },
    )
    assert draft.status_code == 201, draft.text
    confirmed = client.post(f"/api/pharmacy/purchases/{draft.json()['id']}/confirm", headers=auth_headers)
    assert confirmed.status_code == 200, confirmed.text

    blocked = client.post(
        "/api/pharmacy/sales",
        headers=auth_headers,
        json={"payment_type": "cash", "items": [{"medicine_id": mid, "quantity": 1, "rate_tier": "A"}]},
    )
    assert blocked.status_code == 400, blocked.text
    assert "doctor name" in blocked.json()["detail"].lower()

    saved = client.post(
        "/api/pharmacy/sales",
        headers=auth_headers,
        json={
            "payment_type": "cash",
            "doctor_name": "Dr. Rao",
            "items": [{"medicine_id": mid, "quantity": 1, "rate_tier": "A"}],
        },
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["doctor_name"] == "Dr. Rao"
