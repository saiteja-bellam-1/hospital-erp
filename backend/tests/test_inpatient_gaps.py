"""
Gap-coverage tests for the Inpatient module.

The big `test_inpatient_smoke.py` suite covers most of the module, but several
recently-shipped flows had no tests at all. This file fills those gaps:

  * IP-doctor acceptance handshake (accept / reject + clinical lock while pending)
  * Gate pass issuance, the outstanding-bill 409 gate, and the override path
  * Bill reconciliation + the post-finalize "Settle" hint (collect / refund)
  * The credit_refund_required discharge gate (patient overpaid)
  * Payer scheme catalog CRUD + mid-stay payer conversion + history
  * Doctor duty roster CRUD + duty-doctor/on-duty lookup
  * Nursing notes CRUD

Each test class is self-contained: it creates its own room/admission and shares
state via a module-scoped dict. Classes run in definition order; the one
seed_data patient is freed by `_discharge_active` at the start of each class.
"""

from datetime import datetime, date, timedelta

import pytest

from inpatient_test_helpers import discharge_active_admissions, ready_discharge_summary

API = "/api/inpatient"


def _discharge_active(client, headers, patient_id):
    """Discharge any currently-admitted admission for the seed patient so the
    next class can admit cleanly. Mirrors the cleanup in TestInpatientPhase2."""
    discharge_active_admissions(client, headers, patient_id)


# ======================================================================
# IP-doctor acceptance handshake
# ======================================================================
_acc: dict = {}


class TestAdmissionAcceptance:
    """B3 — admissions created with require_acceptance=True start 'pending' and
    lock clinical actions until an IP doctor accepts (or rejects) them."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        r = client.post(
            f"{API}/rooms",
            json={"room_number": "ACC-1", "room_type": "general", "bed_count": 4,
                  "room_charge_per_day": 800.0},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _acc["room_id"] = r.json()["id"]

    def test_admission_starts_pending(self, client, auth_headers, seed_data):
        r = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _acc["room_id"],
                "admission_type": "elective",
                "admission_reason": "Acceptance handshake test",
                "require_acceptance": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["acceptance_status"] == "pending"
        _acc["admission_id"] = r.json()["id"]

    def test_clinical_action_locked_while_pending(self, client, auth_headers):
        """A valid vitals payload must still be rejected with 409 because the
        admission has not been accepted yet."""
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/vitals",
            json={"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": 72,
                  "respiratory_rate": 16, "temperature_c": 36.8, "spo2": 98,
                  "shift": "morning"},
            headers=auth_headers,
        )
        assert r.status_code == 409, r.text
        assert "pending" in str(r.json()["detail"]).lower()

    def test_accept_admission(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/accept",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["acceptance_status"] == "accepted"
        assert body["accepted_at"] is not None

    def test_clinical_action_allowed_after_accept(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/vitals",
            json={"bp_systolic": 118, "bp_diastolic": 78, "heart_rate": 70,
                  "respiratory_rate": 15, "temperature_c": 36.7, "spo2": 99,
                  "shift": "morning"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    def test_double_accept_is_idempotent(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/accept",
            json={}, headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["acceptance_status"] == "accepted"

    def test_reject_after_accept_blocked(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/reject",
            json={"reason": "changed mind"},
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "already accepted" in r.json()["detail"].lower()

    def test_discharge_accepted_admission_to_free_patient(self, client, auth_headers):
        ready_discharge_summary(client, _acc["admission_id"], auth_headers)
        r = client.post(
            f"{API}/admissions/{_acc['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "done",
                  "force_outstanding_balance": True, "override_reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    def test_reject_flow(self, client, auth_headers, seed_data):
        """A fresh pending admission can be rejected; reason is mandatory and
        a rejected admission can no longer be accepted."""
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _acc["room_id"],
                "admission_type": "emergency",
                "require_acceptance": True,
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        adm_id = adm.json()["id"]
        assert adm.json()["acceptance_status"] == "pending"

        # Reason is required (Pydantic min_length=1 -> 422)
        missing = client.post(f"{API}/admissions/{adm_id}/reject", json={},
                              headers=auth_headers)
        assert missing.status_code == 422, missing.text

        ok = client.post(f"{API}/admissions/{adm_id}/reject",
                         json={"reason": "No bed of required type available"},
                         headers=auth_headers)
        assert ok.status_code == 200, ok.text
        assert ok.json()["acceptance_status"] == "rejected"

        # Cannot accept something already rejected
        late = client.post(f"{API}/admissions/{adm_id}/accept", json={},
                           headers=auth_headers)
        assert late.status_code == 400, late.text
        assert "rejected" in late.json()["detail"].lower()


# ======================================================================
# Print-only interim statement (no Bill row / no stamping)
# ======================================================================
_interim_preview: dict = {}


class TestInterimPreviewPdf:
    """Interim Bill UI prints a live PDF with INTERIM watermark — no Bill create."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "IPREV-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 800.0},
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Interim preview PDF test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _interim_preview["admission_id"] = adm.json()["id"]

    def test_as_interim_pdf_does_not_create_bill(self, client, auth_headers):
        adm_id = _interim_preview["admission_id"]
        before = client.get(f"{API}/admissions/{adm_id}/bills", headers=auth_headers)
        assert before.status_code == 200
        count_before = len(before.json())

        pdf = client.get(
            f"{API}/admissions/{adm_id}/bill/pdf",
            params={"as_interim": True},
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content[:4] == b"%PDF"

        after = client.get(f"{API}/admissions/{adm_id}/bills", headers=auth_headers)
        assert after.status_code == 200
        assert len(after.json()) == count_before

        # Charges remain unbilled — balance still includes live unbilled total.
        bal = client.get(f"{API}/admissions/{adm_id}/balance", headers=auth_headers)
        assert bal.status_code == 200
        assert float(bal.json().get("billed_on_bills") or 0) == 0.0


# ======================================================================
# Bill reconciliation + post-finalize Settle hint (collect path)
# ======================================================================
_rec: dict = {}


class TestBillReconciliation:
    """The finalize response carries a Settle hint, and recording a deposit
    that covers the total auto-reconciles the bill to 'paid'."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "REC-1", "room_type": "general", "bed_count": 2,
                  "room_charge_per_day": 1200.0},
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Reconciliation test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _rec["admission_id"] = adm.json()["id"]

        svc = client.post(
            f"{API}/ancillary-services",
            json={"service_name": "CT Scan", "category": "imaging",
                  "default_charge": 3000.0, "charge_unit": "per_session"},
            headers=auth_headers,
        )
        assert svc.status_code == 201, svc.text
        charge = client.post(
            f"{API}/admissions/{_rec['admission_id']}/ancillary-charges",
            json={"service_id": svc.json()["id"], "quantity": 1, "unit_price": 3000.0},
            headers=auth_headers,
        )
        assert charge.status_code == 201, charge.text

    def test_finalize_returns_collect_hint(self, client, auth_headers):
        """With no deposit recorded, finalize should ask the operator to
        collect the full amount."""
        preview = client.get(
            f"{API}/admissions/{_rec['admission_id']}/bill", headers=auth_headers)
        assert preview.status_code == 200, preview.text
        grand_total = preview.json()["grand_total"]
        assert grand_total > 3000.0  # ancillary + at least one room-day

        r = client.post(
            f"{API}/admissions/{_rec['admission_id']}/bill/finalize",
            json={}, headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert abs(body["total_amount"] - grand_total) < 0.01
        assert body["requires_action"] == "collect"
        assert abs(body["amount_to_collect"] - grand_total) < 0.01
        assert body["amount_to_refund"] == 0
        assert body["credit_balance"] < 0  # patient owes
        _rec["bill_total"] = body["total_amount"]
        _rec["bill_id"] = body["bill_id"]

    def test_finalized_bill_starts_pending(self, client, auth_headers):
        r = client.get(f"{API}/admissions/{_rec['admission_id']}/bills",
                        headers=auth_headers)
        assert r.status_code == 200, r.text
        bills = r.json()
        assert len(bills) == 1
        assert bills[0]["status"] == "pending"

    def test_deposit_reconciles_bill_to_paid(self, client, auth_headers):
        """Recording a deposit covering the total flips the bill to 'paid'
        without an explicit Payment row — the deposit pool is folded in."""
        dep = client.post(
            f"{API}/admissions/{_rec['admission_id']}/deposits",
            json={"amount": _rec["bill_total"], "payment_method": "cash",
                  "deposit_type": "initial"},
            headers=auth_headers,
        )
        assert dep.status_code == 201, dep.text

        bills = client.get(f"{API}/admissions/{_rec['admission_id']}/bills",
                           headers=auth_headers)
        assert bills.status_code == 200
        assert all(b["status"] == "paid" for b in bills.json())

        bal = client.get(f"{API}/admissions/{_rec['admission_id']}/balance",
                         headers=auth_headers)
        assert abs(bal.json()["balance"]) < 0.01  # fully settled

    def test_clean_discharge_after_settle(self, client, auth_headers):
        """A settled admission discharges with no force flags / override."""
        ready_discharge_summary(client, _rec["admission_id"], auth_headers)
        r = client.post(
            f"{API}/admissions/{_rec['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Recovered, bill settled"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text


# ======================================================================
# Credit-refund discharge gate (patient overpaid)
# ======================================================================
_cr: dict = {}


class TestCreditRefundGate:
    """When deposits exceed the bill, discharge is blocked with 409
    credit_refund_required until the excess is refunded."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "CR-1", "room_type": "private", "bed_count": 1,
                  "room_charge_per_day": 1000.0},
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Credit refund gate test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _cr["admission_id"] = adm.json()["id"]

    def test_finalize_returns_refund_hint(self, client, auth_headers):
        preview = client.get(
            f"{API}/admissions/{_cr['admission_id']}/bill", headers=auth_headers)
        grand_total = preview.json()["grand_total"]

        # Overpay by a known margin.
        client.post(
            f"{API}/admissions/{_cr['admission_id']}/deposits",
            json={"amount": grand_total + 5000.0, "payment_method": "cash",
                  "deposit_type": "initial"},
            headers=auth_headers,
        )
        r = client.post(
            f"{API}/admissions/{_cr['admission_id']}/bill/finalize",
            json={}, headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["requires_action"] == "refund"
        assert abs(body["amount_to_refund"] - 5000.0) < 0.01
        assert body["credit_balance"] > 0
        _cr["credit"] = body["amount_to_refund"]

    def test_discharge_blocked_credit_refund_required(self, client, auth_headers):
        ready_discharge_summary(client, _cr["admission_id"], auth_headers)
        r = client.post(
            f"{API}/admissions/{_cr['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "attempt"},
            headers=auth_headers,
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "credit_refund_required"
        assert abs(detail["credit_amount"] - _cr["credit"]) < 0.01

    def test_refund_then_discharge_succeeds(self, client, auth_headers):
        refund = client.post(
            f"{API}/admissions/{_cr['admission_id']}/refund",
            json={"amount": _cr["credit"], "payment_method": "cash"},
            headers=auth_headers,
        )
        assert refund.status_code == 201, refund.text

        ready_discharge_summary(client, _cr["admission_id"], auth_headers)
        r = client.post(
            f"{API}/admissions/{_cr['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Refund issued, discharged"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text


# ======================================================================
# Gate pass
# ======================================================================
_gp: dict = {}


class TestGatePass:
    """B6 — printable gate pass. Requires a discharge record, blocks issuance
    while bills are outstanding unless an override reason is supplied."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "GP-1", "room_type": "general", "bed_count": 2,
                  "room_charge_per_day": 900.0},
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        _gp["room_id"] = room.json()["id"]
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _gp["room_id"],
                "admission_type": "elective",
                "admission_reason": "Gate pass test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _gp["owe_admission_id"] = adm.json()["id"]

    def test_gate_pass_before_discharge_rejected(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass",
            json={}, headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "discharge" in r.json()["detail"].lower()

    def test_discharge_owe_admission(self, client, auth_headers):
        ready_discharge_summary(client, _gp["owe_admission_id"], auth_headers)
        r = client.post(
            f"{API}/admissions/{_gp['owe_admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Discharged with balance outstanding",
                  "force_outstanding_balance": True,
                  "force_no_final_bill": True,
                  "override_reason": "Bill to be settled at counter"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    def test_gate_pass_blocked_when_outstanding(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass",
            json={}, headers=auth_headers,
        )
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "outstanding_bill"
        assert detail["outstanding"] > 0

    def test_gate_pass_issued_with_override(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass",
            json={"override_reason": "Insurance claim pending",
                  "vehicle_no": "TS09AB1234", "attendant_name": "R. Kumar"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["override_balance"] is True
        assert body["outstanding_at_issue"] > 0
        assert body["pass_number"].startswith("GP-")
        _gp["pass_number"] = body["pass_number"]

    def test_duplicate_gate_pass_rejected(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass",
            json={"override_reason": "again"}, headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "already issued" in r.json()["detail"].lower()

    def test_get_gate_pass(self, client, auth_headers):
        r = client.get(f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass",
                        headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["pass_number"] == _gp["pass_number"]
        assert r.json()["override_balance"] is True

    def test_gate_pass_pdf(self, client, auth_headers):
        r = client.get(f"{API}/admissions/{_gp['owe_admission_id']}/gate-pass/pdf",
                        headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 100

    def test_clean_gate_pass_no_override(self, client, auth_headers, seed_data):
        """A fully-settled discharged admission gets a gate pass with no
        override flag."""
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _gp["room_id"],
                "admission_type": "elective",
                "admission_reason": "Clean gate pass",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        adm_id = adm.json()["id"]

        preview = client.get(f"{API}/admissions/{adm_id}/bill", headers=auth_headers)
        grand_total = preview.json()["grand_total"]
        client.post(
            f"{API}/admissions/{adm_id}/deposits",
            json={"amount": grand_total, "payment_method": "cash",
                  "deposit_type": "initial"},
            headers=auth_headers,
        )
        final = client.post(
            f"{API}/admissions/{adm_id}/bill/finalize",
            json={},
            headers=auth_headers,
        )
        assert final.status_code == 200, final.text
        ready_discharge_summary(client, adm_id, auth_headers)
        disc = client.post(
            f"{API}/admissions/{adm_id}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Settled and discharged"},
            headers=auth_headers,
        )
        assert disc.status_code == 201, disc.text

        gp = client.post(f"{API}/admissions/{adm_id}/gate-pass", json={},
                         headers=auth_headers)
        assert gp.status_code == 201, gp.text
        assert gp.json()["override_balance"] is False
        assert gp.json()["outstanding_at_issue"] == 0

    def test_zero_balance_with_interim_bill_needs_no_gate_pass_override(
        self, client, auth_headers, seed_data,
    ):
        """A comprehensive final bill replaces interim totals for the exit gate."""
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _gp["room_id"],
                "admission_type": "elective",
                "admission_reason": "Settled comprehensive bill",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        adm_id = adm.json()["id"]

        preview = client.get(f"{API}/admissions/{adm_id}/bill", headers=auth_headers)
        assert preview.status_code == 200, preview.text
        total = float(preview.json()["grand_total"])
        assert total > 0

        interim = client.post(
            f"{API}/admissions/{adm_id}/bill/interim",
            json={},
            headers=auth_headers,
        )
        assert interim.status_code == 200, interim.text

        deposit = client.post(
            f"{API}/admissions/{adm_id}/deposits",
            json={"amount": total, "payment_method": "cash", "deposit_type": "topup"},
            headers=auth_headers,
        )
        assert deposit.status_code == 201, deposit.text

        final = client.post(
            f"{API}/admissions/{adm_id}/bill/finalize",
            json={
                "items_override": [{
                    "source": "custom",
                    "source_id": None,
                    "item_type": "admission_charges",
                    "item_name": "Comprehensive admission charges",
                    "quantity": 1,
                    "unit_price": total,
                    "total_price": total,
                }],
            },
            headers=auth_headers,
        )
        assert final.status_code == 200, final.text

        balance = client.get(
            f"{API}/admissions/{adm_id}/balance", headers=auth_headers,
        )
        assert balance.status_code == 200, balance.text
        assert abs(float(balance.json()["balance"])) <= 0.01

        ready_discharge_summary(client, adm_id, auth_headers)
        disc = client.post(
            f"{API}/admissions/{adm_id}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "discharge_summary": "Settled and discharged",
            },
            headers=auth_headers,
        )
        assert disc.status_code == 201, disc.text

        gp = client.post(
            f"{API}/admissions/{adm_id}/gate-pass", json={}, headers=auth_headers,
        )
        assert gp.status_code == 201, gp.text
        assert gp.json()["override_balance"] is False
        assert gp.json()["outstanding_at_issue"] == 0


# ======================================================================
# Payer schemes + mid-stay payer conversion
# ======================================================================
_pay: dict = {}


class TestPayerSchemes:
    """B1/B2 — payer scheme catalog CRUD and converting an admission's payer
    mid-stay, with an audit trail."""

    def test_create_payer_scheme(self, client, auth_headers):
        r = client.post(
            f"{API}/payer-schemes",
            json={"code": "AAROGYASRI", "name": "Aarogyasri Health Scheme",
                  "scheme_type": "govt_scheme"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["code"] == "AAROGYASRI"
        _pay["scheme_a"] = r.json()["id"]

        r2 = client.post(
            f"{API}/payer-schemes",
            json={"code": "CASH", "name": "Cash / Self Pay", "scheme_type": "cash"},
            headers=auth_headers,
        )
        assert r2.status_code == 201, r2.text
        _pay["scheme_cash"] = r2.json()["id"]

    def test_duplicate_code_rejected(self, client, auth_headers):
        r = client.post(
            f"{API}/payer-schemes",
            json={"code": "AAROGYASRI", "name": "Dup", "scheme_type": "govt_scheme"},
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "already exists" in r.json()["detail"].lower()

    def test_list_payer_schemes(self, client, auth_headers):
        r = client.get(f"{API}/payer-schemes", headers=auth_headers)
        assert r.status_code == 200, r.text
        codes = {s["code"] for s in r.json()}
        assert {"AAROGYASRI", "CASH"} <= codes

    def test_update_payer_scheme(self, client, auth_headers):
        r = client.put(
            f"{API}/payer-schemes/{_pay['scheme_a']}",
            json={"name": "Aarogyasri (Renamed)"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Aarogyasri (Renamed)"

    def test_convert_admission_payer(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "PAY-1", "room_type": "general", "bed_count": 2,
                  "room_charge_per_day": 700.0},
            headers=auth_headers,
        )
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Payer conversion test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _pay["admission_id"] = adm.json()["id"]

        r = client.patch(
            f"{API}/admissions/{_pay['admission_id']}/payer",
            json={"payer_scheme_id": _pay["scheme_a"],
                  "reason": "Patient produced Aarogyasri card",
                  "scheme_member_id": "ASRI-99887"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["payer_scheme_id"] == _pay["scheme_a"]
        assert r.json()["payer_type"] == "govt_scheme"

    def test_payer_history_records_change(self, client, auth_headers):
        # Second conversion: govt scheme rejected, fall back to cash.
        r = client.patch(
            f"{API}/admissions/{_pay['admission_id']}/payer",
            json={"payer_scheme_id": _pay["scheme_cash"],
                  "reason": "Aarogyasri pre-auth rejected"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        hist = client.get(
            f"{API}/admissions/{_pay['admission_id']}/payer-history",
            headers=auth_headers)
        assert hist.status_code == 200, hist.text
        rows = hist.json()
        # Two transitions logged; assert on content (timestamps can tie within
        # the same second, so don't depend on row order).
        assert len(rows) == 2
        to_cash = next(r for r in rows if r["to_payer_type"] == "cash")
        assert to_cash["from_payer_type"] == "govt_scheme"
        assert to_cash["reason"] == "Aarogyasri pre-auth rejected"
        assert any(r["to_payer_type"] == "govt_scheme" for r in rows)

    def test_convert_to_inactive_scheme_rejected(self, client, auth_headers):
        # Deactivate via DELETE (soft-delete) then attempt to convert to it.
        dead = client.post(
            f"{API}/payer-schemes",
            json={"code": "OLDTPA", "name": "Retired TPA", "scheme_type": "tpa"},
            headers=auth_headers,
        )
        dead_id = dead.json()["id"]
        d = client.delete(f"{API}/payer-schemes/{dead_id}", headers=auth_headers)
        assert d.status_code == 204, d.text

        r = client.patch(
            f"{API}/admissions/{_pay['admission_id']}/payer",
            json={"payer_scheme_id": dead_id, "reason": "should fail"},
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "inactive" in r.json()["detail"].lower()

    def test_deleted_scheme_excluded_from_active_list(self, client, auth_headers):
        active = client.get(f"{API}/payer-schemes", headers=auth_headers)
        assert "OLDTPA" not in {s["code"] for s in active.json()}
        allsch = client.get(f"{API}/payer-schemes?active_only=false",
                            headers=auth_headers)
        assert "OLDTPA" in {s["code"] for s in allsch.json()}


# ======================================================================
# Doctor duty roster
# ======================================================================
_dr: dict = {}


class TestDoctorRoster:
    """B4 — per-shift doctor duty roster and the on-duty lookup."""

    def test_create_roster_entry(self, client, auth_headers, seed_data):
        _dr["doctor_id"] = seed_data["doctor_user_id"]
        _dr["roster_date"] = date.today().isoformat()
        r = client.post(
            f"{API}/doctor-roster",
            json={"doctor_id": _dr["doctor_id"], "roster_date": _dr["roster_date"],
                  "shift": "morning", "status": "working", "ward": "ICU"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["shift"] == "morning"
        assert r.json()["doctor_name"] is not None
        _dr["entry_id"] = r.json()["id"]

    def test_double_booking_rejected(self, client, auth_headers):
        r = client.post(
            f"{API}/doctor-roster",
            json={"doctor_id": _dr["doctor_id"], "roster_date": _dr["roster_date"],
                  "shift": "morning", "status": "on_call"},
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text
        assert "already rostered" in r.json()["detail"].lower()

    def test_list_roster(self, client, auth_headers):
        r = client.get(
            f"{API}/doctor-roster?start_date={_dr['roster_date']}"
            f"&end_date={_dr['roster_date']}",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert any(e["id"] == _dr["entry_id"] for e in r.json())

    def test_update_roster_entry(self, client, auth_headers):
        r = client.put(
            f"{API}/doctor-roster/{_dr['entry_id']}",
            json={"status": "on_call", "ward": "General"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "on_call"
        assert r.json()["ward"] == "General"

    def test_duty_doctor_on_duty(self, client, auth_headers):
        """The rostered doctor shows up in the morning-shift on-duty list."""
        at = f"{_dr['roster_date']}T09:00:00"
        r = client.get(f"{API}/duty-doctor/on-duty?at={at}", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["shift"] == "morning"
        assert _dr["doctor_id"] in {d["doctor_id"] for d in body["on_duty"]}

    def test_delete_roster_entry(self, client, auth_headers):
        r = client.delete(f"{API}/doctor-roster/{_dr['entry_id']}",
                          headers=auth_headers)
        assert r.status_code == 204, r.text
        gone = client.get(
            f"{API}/doctor-roster?start_date={_dr['roster_date']}"
            f"&end_date={_dr['roster_date']}",
            headers=auth_headers,
        )
        assert not any(e["id"] == _dr["entry_id"] for e in gone.json())


# ======================================================================
# Nursing notes
# ======================================================================
_nn: dict = {}


class TestNursingNotes:
    """Nursing notes CRUD on an admission."""

    def test_setup(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={"room_number": "NN-1", "room_type": "general", "bed_count": 2,
                  "room_charge_per_day": 600.0},
            headers=auth_headers,
        )
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Nursing notes test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _nn["admission_id"] = adm.json()["id"]

    def test_create_nursing_note(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_nn['admission_id']}/nursing-notes",
            json={"shift": "morning", "note_type": "observation",
                  "content": "Patient comfortable, vitals stable."},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["note_type"] == "observation"
        assert r.json()["nurse_name"] is not None
        _nn["note_id"] = r.json()["id"]

    def test_invalid_note_type_rejected(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_nn['admission_id']}/nursing-notes",
            json={"shift": "morning", "note_type": "not_a_type", "content": "x"},
            headers=auth_headers,
        )
        assert r.status_code == 422, r.text

    def test_list_nursing_notes(self, client, auth_headers):
        r = client.get(
            f"{API}/admissions/{_nn['admission_id']}/nursing-notes",
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert any(n["id"] == _nn["note_id"] for n in r.json())

    def test_update_nursing_note(self, client, auth_headers):
        r = client.put(
            f"{API}/nursing-notes/{_nn['note_id']}",
            json={"content": "Updated: patient reports mild pain (3/10).",
                  "note_type": "general"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["content"].startswith("Updated:")
        assert r.json()["note_type"] == "general"

    def test_delete_nursing_note(self, client, auth_headers):
        r = client.delete(f"{API}/nursing-notes/{_nn['note_id']}",
                          headers=auth_headers)
        assert r.status_code == 204, r.text
        gone = client.get(
            f"{API}/admissions/{_nn['admission_id']}/nursing-notes",
            headers=auth_headers)
        assert not any(n["id"] == _nn["note_id"] for n in gone.json())


# ======================================================================
# Cleanup — runs last so the shared-session seed patient is left
# un-admitted, exactly as the other test files leave it. The smoke suite
# admits this patient from a clean slate, so a leftover active admission
# from this file would cascade-fail it.
# ======================================================================
class TestGapsCleanup:
    def test_discharge_seed_patient(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        r = client.get(
            f"{API}/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers)
        assert r.status_code == 200
        assert not any(a.get("status") == "admitted" for a in r.json())
