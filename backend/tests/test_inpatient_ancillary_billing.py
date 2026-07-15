"""Regression tests for inpatient ancillary billing fixes.

Covers:
- Decimal quantity preserved on BillItem
- Final PDF uses saved BillItem name/rate/amount (not live catalog)
- Historical bill_id PDF returns that bill's items
- Comprehensive finalize settlement does not double-count interim totals
"""

from io import BytesIO

from PyPDF2 import PdfReader

_state: dict = {}


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _discharge_active(client, auth_headers, patient_id):
    """Clear any active admission. against_advice bypasses summary/balance gates."""
    existing = client.get(
        f"/api/inpatient/admissions/patient/{patient_id}",
        headers=auth_headers,
    )
    if existing.status_code != 200:
        return
    for adm in existing.json():
        if adm.get("status") == "admitted":
            client.post(
                f"/api/inpatient/admissions/{adm['id']}/discharge",
                json={
                    "discharge_type": "against_advice",
                    "condition_on_discharge": "stable",
                    "discharge_summary": "Auto-discharged for ancillary billing test",
                    "force_outstanding_balance": True,
                    "force_unacknowledged_alerts": True,
                    "force_missing_consents": True,
                    "force_no_final_bill": True,
                    "override_reason": "test cleanup",
                },
                headers=auth_headers,
            )


def _ensure_service(client, auth_headers):
    if _state.get("service_id"):
        return _state["service_id"]
    svc = client.post(
        "/api/inpatient/ancillary-services",
        json={
            "service_name": "Physiotherapy Session",
            "category": "physiotherapy",
            "default_charge": 400.0,
            "charge_unit": "per_session",
        },
        headers=auth_headers,
    )
    assert svc.status_code == 201, svc.text
    _state["service_id"] = svc.json()["id"]
    return _state["service_id"]


def _admit(client, auth_headers, seed_data, room_number, room_rate=500.0):
    _discharge_active(client, auth_headers, seed_data["patient_id"])
    room = client.post(
        "/api/inpatient/rooms",
        json={
            "room_number": room_number,
            "room_type": "general",
            "bed_count": 1,
            "room_charge_per_day": room_rate,
        },
        headers=auth_headers,
    )
    assert room.status_code == 201, room.text
    adm = client.post(
        "/api/inpatient/admissions",
        json={
            "patient_id": seed_data["patient_id"],
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room.json()["id"],
            "admission_type": "elective",
            "admission_reason": "Ancillary billing regression",
            "condition_on_admission": "stable",
        },
        headers=auth_headers,
    )
    assert adm.status_code == 201, adm.text
    return adm.json()["id"]


class TestAncillaryBillingFixes:
    def test_setup(self, client, auth_headers, seed_data):
        _state["admission_id"] = _admit(client, auth_headers, seed_data, "ANC-501", 500.0)

        d = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/deposits",
            json={"amount": 1000.0, "payment_method": "cash", "deposit_type": "initial"},
            headers=auth_headers,
        )
        assert d.status_code == 201, d.text
        _ensure_service(client, auth_headers)

    def test_decimal_quantity_charge_and_bill_item(self, client, auth_headers, TestSessionLocal):
        service_id = _ensure_service(client, auth_headers)
        r = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/ancillary-charges",
            json={
                "service_id": service_id,
                "quantity": 2.5,
                "unit_price": 400.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert float(data["quantity"]) == 2.5
        assert float(data["total_amount"]) == 1000.0
        _state["ancillary_charge_id"] = data["id"]

        items = [
            {
                "source": "ancillary",
                "source_id": data["id"],
                "item_type": "ancillary",
                "item_name": "Physiotherapy Session (physiotherapy)",
                "quantity": 2.5,
                "unit_price": 400.0,
                "total_price": 1000.0,
            },
        ]
        fin = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            json={"items_override": items},
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        _state["final_bill_id"] = fin.json()["bill_id"]

        from app.models.billing import BillItem
        db = TestSessionLocal()
        try:
            anc_item = (
                db.query(BillItem)
                .filter(
                    BillItem.bill_id == _state["final_bill_id"],
                    BillItem.item_type == "ancillary",
                )
                .first()
            )
            assert anc_item is not None
            assert float(anc_item.quantity) == 2.5
            assert float(anc_item.unit_price) == 400.0
            assert float(anc_item.total_price) == 1000.0
            assert "Physiotherapy" in anc_item.item_name
        finally:
            db.close()

    def test_pdf_uses_saved_bill_items_not_catalog_rename(self, client, auth_headers):
        service_id = _ensure_service(client, auth_headers)
        assert _state.get("final_bill_id"), "prior finalize required"

        upd = client.put(
            f"/api/inpatient/ancillary-services/{service_id}",
            json={"service_name": "RENAMED Physio — should not appear on old bill"},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text

        pdf = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/pdf",
            params={"bill_id": _state["final_bill_id"]},
            headers=auth_headers,
        )
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"

        text = _pdf_text(pdf.content)
        assert "Physiotherapy Session" in text
        assert "RENAMED Physio" not in text
        assert "400.00" in text
        assert "1,000.00" in text or "1000.00" in text

    def test_historical_bill_id_isolation(self, client, auth_headers, seed_data):
        service_id = _ensure_service(client, auth_headers)
        adm_id = _admit(client, auth_headers, seed_data, "ANC-502", 800.0)

        client.post(
            f"/api/inpatient/admissions/{adm_id}/deposits",
            json={"amount": 20000.0, "payment_method": "cash"},
            headers=auth_headers,
        )

        ch1 = client.post(
            f"/api/inpatient/admissions/{adm_id}/ancillary-charges",
            json={"service_id": service_id, "quantity": 1, "unit_price": 250.0},
            headers=auth_headers,
        )
        assert ch1.status_code == 201, ch1.text

        interim = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/interim",
            json={},
            headers=auth_headers,
        )
        assert interim.status_code == 200, interim.text
        interim_id = interim.json()["bill_id"]

        ch2 = client.post(
            f"/api/inpatient/admissions/{adm_id}/ancillary-charges",
            json={"service_id": service_id, "quantity": 1, "unit_price": 777.0},
            headers=auth_headers,
        )
        assert ch2.status_code == 201, ch2.text

        pdf = client.get(
            f"/api/inpatient/admissions/{adm_id}/bill/pdf",
            params={"bill_id": interim_id},
            headers=auth_headers,
        )
        assert pdf.status_code == 200
        text = _pdf_text(pdf.content)
        assert "250.00" in text
        assert "777.00" not in text

    def test_comprehensive_finalize_settlement_no_double_count(
        self, client, auth_headers, seed_data
    ):
        service_id = _ensure_service(client, auth_headers)
        adm_id = _admit(client, auth_headers, seed_data, "ANC-503", 1000.0)

        client.post(
            f"/api/inpatient/admissions/{adm_id}/deposits",
            json={"amount": 1500.0, "payment_method": "cash"},
            headers=auth_headers,
        )

        ch = client.post(
            f"/api/inpatient/admissions/{adm_id}/ancillary-charges",
            json={"service_id": service_id, "quantity": 1, "unit_price": 500.0},
            headers=auth_headers,
        )
        assert ch.status_code == 201, ch.text
        charge_id = ch.json()["id"]

        interim = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/interim",
            json={},
            headers=auth_headers,
        )
        assert interim.status_code == 200, interim.text
        interim_total = float(interim.json()["total_amount"])

        bal = client.get(
            f"/api/inpatient/admissions/{adm_id}/balance",
            headers=auth_headers,
        ).json()
        prior_billed = float(bal["billed_on_bills"])
        assert prior_billed == interim_total

        items = [
            {
                "source": "ancillary",
                "source_id": charge_id,
                "item_type": "ancillary",
                "item_name": "Physiotherapy Session (physiotherapy)",
                "quantity": 1,
                "unit_price": 500.0,
                "total_price": 500.0,
            },
            {
                "source": "room",
                "source_id": None,
                "item_type": "room_charge",
                "item_name": "Room rent",
                "quantity": 1,
                "unit_price": 1000.0,
                "total_price": 1000.0,
            },
        ]
        comprehensive = 1500.0

        fin = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/finalize",
            json={"items_override": items},
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        assert abs(float(fin.json()["total_amount"]) - comprehensive) < 0.01
