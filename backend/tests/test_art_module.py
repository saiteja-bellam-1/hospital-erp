"""Fertility (ART) flows.

Phase 1 — front desk, case, workup, IUI, stimulation, consents, both billing modes.
Phase 2 — embryology, witnessing, cryostorage, Level 2 licence gate.
Phase 3 — in-house bank, outside receipt, registry export.
Phase 4 — outcomes, lab indicators, equipment, grievances.
"""
import os
import tempfile
from datetime import date, datetime, timedelta

import pytest

from app.models.billing import Bill
from app.models.license import License
from app.models.permissions import RoleModulePermission
from app.models.user import User, UserRole
from app.services.db_seed import _ART_FRONTDESK
from app.services.trial import clear_isolated_store, use_isolated_store
from app.utils.auth import create_access_token, get_password_hash


MALE_NAMES = {"Arun", "Dev", "Nikhil"}


def _headers(username):
    token = create_access_token(data={"sub": username})
    return {"Authorization": f"Bearer {token}"}


def _patient(client, headers, first, phone, dob="1992-04-02"):
    res = client.post("/api/patients/", headers=headers, json={
        "first_name": first,
        "last_name": "Fertility",
        "primary_phone": phone,
        "date_of_birth": dob,
        "gender": "male" if first in MALE_NAMES else "female",
    })
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _user(db, hospital_id, username, role_name, permissions):
    role = db.query(UserRole).filter_by(name=role_name).first()
    if role is None:
        role = UserRole(name=role_name, is_system_role=True)
        db.add(role)
        db.flush()
    grant = db.query(RoleModulePermission).filter_by(role_id=role.id, module_name="art").first()
    if grant is None:
        db.add(RoleModulePermission(role_id=role.id, module_name="art", permissions=list(permissions)))
    else:
        grant.permissions = list(permissions)
    user = db.query(User).filter_by(username=username).first()
    if user is None:
        user = User(
            username=username,
            password_hash=get_password_hash("art-pass-1"),
            email=f"{username}@test.com",
            first_name=username,
            last_name="User",
            role_id=role.id,
            hospital_id=hospital_id,
            is_active=True,
        )
        db.add(user)
    db.commit()
    return user


@pytest.fixture(autouse=True)
def _doctor_can_witness(seed_data, db_session):
    """The seeded doctor acts as the second-person witness in these flows."""
    doctor = db_session.query(User).filter(User.id == seed_data["doctor_user_id"]).one()
    grant = db_session.query(RoleModulePermission).filter_by(role_id=doctor.role_id, module_name="art").first()
    if grant is None:
        db_session.add(RoleModulePermission(role_id=doctor.role_id, module_name="art", permissions=["view_art", "witness_lab"]))
    else:
        grant.permissions = sorted(set(grant.permissions or []) | {"view_art", "witness_lab"})
    db_session.commit()


def test_phase1_frontdesk_case_cycle_and_billing(client, seed_data, db_session):
    admin = _headers("testadmin")
    desk_user = _user(db_session, seed_data["hospital_id"], "artfrontdesk", "art_frontdesk", _ART_FRONTDESK)
    desk = _headers(desk_user.username)
    reception = _headers("testreceptionist")

    # Hospital reception is not the fertility desk.
    denied = client.get("/api/art/cases", headers=reception)
    assert denied.status_code == 403

    centre = client.put("/api/art/centre", headers=admin, json={
        "clinic_level": 1,
        "clinic_registration_no": "ART-L1-1",
        "director_name": "Dr Meera",
        "bank_enabled": True,
        "bank_registration_no": "BANK-1",
    })
    assert centre.status_code == 200, centre.text
    assert centre.json()["clinic_level"] == 1
    assert centre.json()["lab_enabled"] is False

    scan = client.post("/api/art/services", headers=admin, json={
        "code": "SCAN", "name": "Follicle scan", "default_price": 800, "requires_level": 1,
    })
    iui = client.post("/api/art/services", headers=admin, json={
        "code": "IUI", "name": "IUI", "default_price": 5000, "requires_level": 1,
    })
    assert scan.status_code == 200 and iui.status_code == 200

    package = client.post("/api/art/packages", headers=admin, json={
        "name": "IUI package",
        "code": "IUI-PKG",
        "price": 50000,
        "included_service_codes": ["SCAN", "IUI"],
        "includes_medicines": False,
        "cancel_keep_amount": 5000,
    })
    assert package.status_code == 200, package.text
    package_id = package.json()["id"]

    # Front desk cannot edit the package catalog.
    assert client.post("/api/art/packages", headers=desk, json={
        "name": "Nope", "price": 1,
    }).status_code == 403

    woman = _patient(client, admin, "Anika", "9000000011", "1992-04-02")
    partner = _patient(client, admin, "Arun", "9000000012", "1990-01-15")
    case = client.post("/api/art/cases", headers=desk, json={
        "case_type": "couple",
        "woman_patient_id": woman,
        "partner_patient_id": partner,
    })
    assert case.status_code == 200, case.text
    case_id = case.json()["id"]
    assert case.json()["case_number"].startswith("ART-")

    consent_pdf = client.get(
        f"/api/art/cases/{case_id}/consent-form.pdf",
        headers=desk,
        params={"form_code": "iui_husband"},
    )
    assert consent_pdf.status_code == 200, consent_pdf.text
    assert consent_pdf.content.startswith(b"%PDF")
    assert "attachment" in consent_pdf.headers["content-disposition"]
    donor_form = client.get(
        f"/api/art/cases/{case_id}/consent-form.pdf",
        headers=desk,
        params={"form_code": "donor_oocyte"},
    )
    assert donor_form.status_code == 400
    assert "donor bank" in donor_form.json()["detail"].lower()

    workup = client.put(f"/api/art/cases/{case_id}/workup", headers=admin, json={
        "infertility_years": 3,
        "amh": 2.1,
        "antral_follicle_count": 12,
        "semen_summary": "Count 18 million",
        "diagnosis": "Unexplained",
        "treatment_plan": "IUI",
    })
    assert workup.status_code == 200, workup.text
    # Front desk does not write the clinical workup.
    assert client.put(f"/api/art/cases/{case_id}/workup", headers=desk, json={"diagnosis": "x"}).status_code == 403

    note = client.post(f"/api/art/cases/{case_id}/notes", headers=admin, json={"note": "Counselled on IUI."})
    assert note.status_code == 200, note.text

    uploaded = client.post(
        f"/api/art/cases/{case_id}/documents",
        headers=desk,
        data={"document_name": "AMH report", "document_type": "report"},
        files={"file": ("amh.txt", b"amh 2.1", "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    download = client.get(f"/api/art/documents/{uploaded.json()['id']}/download", headers=desk)
    assert download.status_code == 200
    assert download.content == b"amh 2.1"

    token = client.post("/api/art/queue", headers=desk, json={"case_id": case_id})
    assert token.status_code == 200, token.text
    assert token.json()["token_no"] >= 1

    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=desk, json={
        "cycle_type": "iui_husband",
        "protocol": "natural",
        "billing_mode": "package",
        "package_template_id": package_id,
        "collect_advance": True,
        "payment_method": "cash",
        "clinician_id": seed_data["doctor_user_id"],
    })
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]
    assert cycle.json()["estimate_snapshot"]["billing_mode"] == "package"
    assert cycle.json()["agreed_price"] == 50000

    pdf = client.get(f"/api/art/cycles/{cycle_id}/estimate.pdf", headers=desk)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")

    stim = client.post(f"/api/art/cycles/{cycle_id}/stimulation", headers=admin, json={
        "day_number": 8,
        "drugs": [{"name": "Gonadotropin", "dose": "75 IU", "route": "SC"}],
        "follicles_left": [14, 16],
        "follicles_right": [15],
        "endometrium_mm": 8.2,
        "e2": 420,
        "lh": 4.1,
        "progesterone": 0.4,
    })
    assert stim.status_code == 200, stim.text
    trigger = client.post(f"/api/art/cycles/{cycle_id}/trigger", headers=admin, json={
        "drug": "hCG 5000",
        "trigger_at": datetime.now().isoformat(),
    })
    assert trigger.status_code == 200, trigger.text

    # Consent gates the IUI booking.
    blocked = client.post("/api/art/appointments", headers=desk, json={
        "case_id": case_id, "cycle_id": cycle_id, "kind": "iui", "scheduled_date": date.today().isoformat(),
    })
    assert blocked.status_code == 400
    assert "consent" in blocked.json()["detail"].lower()

    consent = client.post(f"/api/art/cases/{case_id}/consents", headers=desk, json={
        "form_code": "iui_husband", "signed_by_name": "Anika Fertility", "cycle_id": cycle_id,
    })
    assert consent.status_code == 200, consent.text

    appt = client.post("/api/art/appointments", headers=desk, json={
        "case_id": case_id, "cycle_id": cycle_id, "kind": "iui",
        "scheduled_date": date.today().isoformat(), "scheduled_time": "10:30", "room": "IUI-1",
    })
    assert appt.status_code == 200, appt.text
    appt_id = appt.json()["id"]

    early = client.post(f"/api/art/appointments/{appt_id}/complete", headers=desk)
    assert early.status_code == 400
    assert "time-out" in early.json()["detail"].lower()

    timeout = client.post(f"/api/art/appointments/{appt_id}/timeout", headers=desk, json={
        "patient_name": "Anika Fertility",
        "dob_confirmed": True,
        "witness_id": seed_data["doctor_user_id"],
    })
    assert timeout.status_code == 200, timeout.text
    done = client.post(f"/api/art/appointments/{appt_id}/complete", headers=desk)
    assert done.status_code == 200, done.text


    covered = client.post(f"/api/art/cycles/{cycle_id}/charges", headers=desk, json={
        "service_code": "SCAN", "kind": "service",
    })
    assert covered.status_code == 200, covered.text
    assert covered.json()["covered_by_package"] is True
    assert covered.json()["bill_id"] is None

    medicine = client.post(f"/api/art/cycles/{cycle_id}/charges", headers=desk, json={
        "kind": "medicine", "description": "Gonadotropin", "amount": 2500,
    })
    assert medicine.status_code == 200, medicine.text
    assert medicine.json()["covered_by_package"] is False
    assert medicine.json()["bill_id"]

    # Front desk cannot switch the commercial mode. Billing admin (here super admin) can.
    forbidden_mode = client.post(f"/api/art/cycles/{cycle_id}/billing-mode", headers=desk, json={
        "billing_mode": "itemised", "reason": "patient asked",
    })
    assert forbidden_mode.status_code == 403
    missing_reason = client.post(f"/api/art/cycles/{cycle_id}/billing-mode", headers=admin, json={
        "billing_mode": "itemised", "reason": "  ",
    })
    assert missing_reason.status_code == 400
    # The advance is already paid, so switching to itemised is refused (cancel refunds it instead).
    switched = client.post(f"/api/art/cycles/{cycle_id}/billing-mode", headers=admin, json={
        "billing_mode": "itemised", "reason": "Patient asked to pay each visit",
    })
    assert switched.status_code == 400, switched.text
    assert "advance has been paid" in switched.json()["detail"]

    cancelled = client.post(f"/api/art/cycles/{cycle_id}/cancel", headers=admin, json={
        "reason": "Patient postponed",
    })
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    refund_id = cancelled.json()["refund_bill_id"]
    assert refund_id
    refund = db_session.query(Bill).filter(Bill.id == refund_id).one()
    assert refund.bill_type == "credit_note"
    assert refund.total_amount == -45000

    # Itemised cycle: pending charges void on cancel, and a paid line would remain.
    woman2 = _patient(client, admin, "Diya", "9000000013", "1988-06-01")
    case2 = client.post("/api/art/cases", headers=desk, json={
        "case_type": "single_woman", "woman_patient_id": woman2,
    })
    assert case2.status_code == 200, case2.text
    itemised = client.post(f"/api/art/cases/{case2.json()['id']}/cycles", headers=desk, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    })
    assert itemised.status_code == 200, itemised.text
    item_cycle = itemised.json()["id"]
    extra = client.post(f"/api/art/cycles/{item_cycle}/charges", headers=desk, json={"service_code": "SCAN"})
    assert extra.status_code == 200, extra.text
    assert extra.json()["covered_by_package"] is False
    bill = db_session.query(Bill).filter(Bill.id == extra.json()["bill_id"]).one()
    assert bill.status == "pending"
    voided = client.post(f"/api/art/cycles/{item_cycle}/cancel", headers=admin, json={"reason": "Did not start"})
    assert voided.status_code == 200, voided.text
    db_session.expire_all()
    bill = db_session.query(Bill).filter(Bill.id == extra.json()["bill_id"]).one()
    assert bill.status == "cancelled"

    board = client.get("/api/art/board", headers=desk)
    assert board.status_code == 200, board.text
    assert any(row["kind"] == "iui" for row in board.json()["appointments"])
    assert board.json()["queue"]

    meds = client.post("/api/art/packages", headers=admin, json={
        "name": "IUI with medicines",
        "price": 10000,
        "included_service_codes": ["IUI"],
        "includes_medicines": True,
        "medicine_limit": 1000,
        "cancel_keep_amount": 0,
    })
    assert meds.status_code == 200, meds.text
    woman3 = _patient(client, admin, "Nisha", "9000000014")
    case3 = client.post("/api/art/cases", headers=desk, json={
        "case_type": "single_woman", "woman_patient_id": woman3,
    })
    med_cycle = client.post(f"/api/art/cases/{case3.json()['id']}/cycles", headers=desk, json={
        "cycle_type": "oi",
        "billing_mode": "package",
        "package_template_id": meds.json()["id"],
        "collect_advance": False,
    })
    assert med_cycle.status_code == 200, med_cycle.text
    med_id = med_cycle.json()["id"]
    inside = client.post(f"/api/art/cycles/{med_id}/charges", headers=desk, json={
        "kind": "medicine", "description": "Follicle drug", "amount": 600,
    })
    assert inside.status_code == 200, inside.text
    assert inside.json()["covered_by_package"] is True
    excess = client.post(f"/api/art/cycles/{med_id}/charges", headers=desk, json={
        "kind": "medicine", "description": "Extra drug", "amount": 700,
    })
    assert excess.status_code == 200, excess.text
    assert excess.json()["covered_by_package"] is False
    assert excess.json()["bill_id"]

    client.post(f"/api/art/cases/{case3.json()['id']}/consents", headers=desk, json={
        "form_code": "iui_donor", "signed_by_name": "Nisha Fertility",
    })
    client.post(f"/api/art/cases/{case3.json()['id']}/consents", headers=admin, json={
        "form_code": "withdrawal", "signed_by_name": "Nisha Fertility",
    })
    # This case is single-woman, so husband IUI is refused. Use a fresh couple for withdrawal.
    woman4 = _patient(client, admin, "Kiran", "9000000015")
    partner4 = _patient(client, admin, "Dev", "9000000016")
    case4 = client.post("/api/art/cases", headers=desk, json={
        "case_type": "couple", "woman_patient_id": woman4, "partner_patient_id": partner4,
    })
    cyc4 = client.post(f"/api/art/cases/{case4.json()['id']}/cycles", headers=desk, json={
        "cycle_type": "iui_husband", "billing_mode": "itemised",
    })
    client.post(f"/api/art/cases/{case4.json()['id']}/consents", headers=desk, json={
        "form_code": "iui_husband", "signed_by_name": "Kiran Fertility",
    })
    client.post(f"/api/art/cases/{case4.json()['id']}/consents", headers=admin, json={
        "form_code": "withdrawal", "signed_by_name": "Kiran Fertility",
    })
    withdrawn = client.post("/api/art/appointments", headers=desk, json={
        "case_id": case4.json()["id"],
        "cycle_id": cyc4.json()["id"],
        "kind": "iui",
        "scheduled_date": date.today().isoformat(),
    })
    assert withdrawn.status_code == 400
    assert "withdrawn" in withdrawn.json()["detail"].lower() or "consent" in withdrawn.json()["detail"].lower()


def test_phase2_embryology_witness_and_cryo(client, seed_data, db_session):
    admin = _headers("testadmin")
    woman = _patient(client, admin, "Lata", "9000000021", "1991-02-02")
    partner = _patient(client, admin, "Nikhil", "9000000022", "1989-03-03")
    case = client.post("/api/art/cases", headers=admin, json={
        "case_type": "couple", "woman_patient_id": woman, "partner_patient_id": partner,
    })
    assert case.status_code == 200, case.text
    case_id = case.json()["id"]

    client.put("/api/art/centre", headers=admin, json={"clinic_level": 1, "bank_enabled": True})
    blocked = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "ivf", "billing_mode": "itemised",
    })
    assert blocked.status_code == 403

    client.put("/api/art/centre", headers=admin, json={"clinic_level": 2, "bank_enabled": True})
    folder = tempfile.mkdtemp()
    use_isolated_store(folder)
    lic = License(
        license_id="LIC-ART-NOLAB",
        hospital_id="HOSP01",
        hospital_name="Test",
        features=["art"],
        issued_at=datetime.utcnow() - timedelta(days=1),
        expires_at=datetime.utcnow() + timedelta(days=30),
        raw_license_data="test-art",
        status="active",
    )
    db_session.add(lic)
    db_session.commit()
    try:
        no_lab = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
            "cycle_type": "ivf", "billing_mode": "itemised", "protocol": "antagonist",
        })
        assert no_lab.status_code == 403, no_lab.text
        assert "art_lab" in no_lab.json()["detail"]
    finally:
        db_session.delete(lic)
        db_session.commit()
        clear_isolated_store()

    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "ivf", "billing_mode": "itemised", "protocol": "antagonist",
        "clinician_id": seed_data["doctor_user_id"],
    })
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]

    early = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json={
        "witness_id": seed_data["doctor_user_id"], "oocytes_retrieved": 8,
    })
    assert early.status_code == 400
    assert "trigger" in early.json()["detail"].lower()
    assert client.post(f"/api/art/cycles/{cycle_id}/trigger", headers=admin, json={
        "drug": "hCG 10000", "trigger_at": datetime.now().isoformat(),
    }).status_code == 200
    no_consent = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json={
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
        "follicles_aspirated": 10,
        "oocytes_retrieved": 8,
        "mature_mii": 6,
        "intermediate_mi": 1,
        "immature_gv": 1,
    })
    assert no_consent.status_code == 400
    client.post(f"/api/art/cases/{case_id}/consents", headers=admin, json={
        "form_code": "oocyte_retrieval", "signed_by_name": "Lata Fertility",
    })
    same = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json={
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["admin_user_id"],
        "oocytes_retrieved": 8,
    })
    assert same.status_code == 400
    retrieved = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json={
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
        "follicles_aspirated": 10,
        "oocytes_retrieved": 8,
        "mature_mii": 6,
    })
    assert retrieved.status_code == 200, retrieved.text

    fert = client.post(f"/api/art/cycles/{cycle_id}/fertilisation", headers=admin, json={
        "method": "icsi",
        "oocytes_inseminated": 6,
        "normally_fertilised": 4,
        "media_lots": ["LOT-OIL-1", "LOT-MED-2"],
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert fert.status_code == 200, fert.text
    assert fert.json()["fert_method"] == "icsi"

    closed = client.post(f"/api/art/cycles/{cycle_id}/specimens", headers=admin, json={"sample_type": "embryo"})
    assert closed.status_code == 400
    opened = client.post(f"/api/art/cycles/{cycle_id}/culture/open", headers=admin)
    assert opened.status_code == 200, opened.text

    other = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "icsi", "billing_mode": "itemised",
    })
    assert other.status_code == 200, other.text
    bench = client.post(f"/api/art/cycles/{other.json()['id']}/culture/open", headers=admin)
    assert bench.status_code == 409

    embryo = client.post(f"/api/art/cycles/{cycle_id}/specimens", headers=admin, json={"sample_type": "embryo"})
    assert embryo.status_code == 200, embryo.text
    embryo_id = embryo.json()["id"]
    assert embryo.json()["owner_case_id"] == case_id
    client.post(f"/api/art/specimens/{embryo_id}/grade", headers=admin, json={"day": 3, "grade": "8A", "stage": "cleavage"})
    graded = client.post(f"/api/art/specimens/{embryo_id}/grade", headers=admin, json={"day": 5, "grade": "4AA", "stage": "blastocyst"})
    assert graded.status_code == 200, graded.text

    # A second embryo is frozen, then thawed into a new FET cycle.
    second = client.post(f"/api/art/cycles/{cycle_id}/specimens", headers=admin, json={"sample_type": "embryo"})
    second_id = second.json()["id"]
    no_freeze_consent = client.post(f"/api/art/specimens/{second_id}/dispose", headers=admin, json={
        "disposition": "freeze", "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
        "tank": "T1", "canister": "C1", "cane": "N1", "position": "1",
    })
    assert no_freeze_consent.status_code == 400
    client.post(f"/api/art/cases/{case_id}/consents", headers=admin, json={
        "form_code": "embryo_freeze", "signed_by_name": "Lata Fertility",
    })
    frozen = client.post(f"/api/art/specimens/{second_id}/dispose", headers=admin, json={
        "disposition": "freeze", "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
        "tank": "T1", "canister": "C1", "cane": "N1", "position": "1",
    })
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["disposition"] == "frozen"

    far = (date.today() + timedelta(days=3650 + 30)).isoformat()
    too_long = client.post(f"/api/art/specimens/{second_id}/renew", headers=admin, json={"renewal_due": far})
    assert too_long.status_code == 400
    allowed = client.post(f"/api/art/specimens/{second_id}/renew", headers=admin, json={
        "renewal_due": far, "oncofertility": True,
    })
    assert allowed.status_code == 200, allowed.text

    moved = client.post(f"/api/art/specimens/{second_id}/owner", headers=admin, json={"case_id": case_id})
    assert moved.status_code == 400

    thawed = client.post(f"/api/art/specimens/{second_id}/thaw", headers=admin, json={
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
        "survived": True,
    })
    assert thawed.status_code == 200, thawed.text
    assert thawed.json()["cycle_type"] == "fet"
    assert thawed.json()["survived"] is True

    no_discard = client.post(f"/api/art/specimens/{embryo_id}/dispose", headers=admin, json={
        "disposition": "discard",
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert no_discard.status_code == 400
    client.post(f"/api/art/cases/{case_id}/consents", headers=admin, json={
        "form_code": "discard", "signed_by_name": "Lata Fertility",
    })
    discarded = client.post(f"/api/art/specimens/{embryo_id}/dispose", headers=admin, json={
        "disposition": "discard",
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert discarded.status_code == 200, discarded.text

    tank = client.post("/api/art/cryo/tank-log", headers=admin, json={
        "tank_name": "T1", "nitrogen_level": "full", "temperature_c": -196, "alarm": False,
    })
    assert tank.status_code == 200, tank.text

    # Front desk cannot open the lab worksheet.
    desk_user = _user(db_session, seed_data["hospital_id"], "artfrontdesk", "art_frontdesk", _ART_FRONTDESK)
    lab_denied = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=_headers(desk_user.username), json={
        "operator_id": seed_data["admin_user_id"], "witness_id": seed_data["doctor_user_id"],
    })
    assert lab_denied.status_code == 403


def test_phase3_bank_inside_outside_and_registry(client, seed_data, db_session):
    admin = _headers("testadmin")
    desk_user = _user(db_session, seed_data["hospital_id"], "artfrontdesk", "art_frontdesk", _ART_FRONTDESK)
    desk = _headers(desk_user.username)
    client.put("/api/art/centre", headers=admin, json={
        "clinic_level": 2, "bank_enabled": True, "bank_registration_no": "BANK-9",
    })

    hidden = client.get("/api/art/donors", headers=desk)
    assert hidden.status_code == 403

    donor = client.post("/api/art/donors", headers=admin, json={
        "donor_type": "oocyte",
        "legal_name": "Private Donor",
        "phone": "9000000099",
        "address": "Lane 4",
        "date_of_birth": "1995-05-05",
    })
    assert donor.status_code == 200, donor.text
    donor_id = donor.json()["id"]
    code = donor.json()["donor_code"]
    assert donor.json()["legal_name"] == "Private Donor"

    donor_pdf = client.get(f"/api/art/donors/{donor_id}/consent-form.pdf", headers=admin)
    assert donor_pdf.status_code == 200, donor_pdf.text
    assert donor_pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/art/donors/{donor_id}/consent-form.pdf", headers=desk).status_code == 403

    codes = client.get("/api/art/donors/codes", headers=desk)
    assert codes.status_code == 200, codes.text
    public = next(row for row in codes.json() if row["donor_code"] == code)
    assert "legal_name" not in public
    assert "phone" not in public

    uncleared = client.post(f"/api/art/donors/{donor_id}/clear", headers=admin)
    assert uncleared.status_code == 400
    client.post(f"/api/art/donors/{donor_id}/screening", headers=admin, json={
        "hiv": "non_reactive", "hbsag": "non_reactive", "hcv": "non_reactive", "vdrl": "non_reactive",
    })
    still = client.post(f"/api/art/donors/{donor_id}/clear", headers=admin)
    assert still.status_code == 400
    assert "insurance" in still.json()["detail"].lower()
    client.post(f"/api/art/donors/{donor_id}/insurance", headers=admin, json={
        "policy_no": "INS-12",
        "valid_until": (date.today() + timedelta(days=400)).isoformat(),
        "amount": 200000,
    })
    cleared = client.post(f"/api/art/donors/{donor_id}/clear", headers=admin)
    assert cleared.status_code == 200, cleared.text

    counted = client.post(f"/api/art/donors/{donor_id}/retrieval", headers=admin, json={"oocytes_retrieved": 8})
    assert counted.status_code == 200, counted.text
    assert counted.json()["over_intended_cap"] is True

    unit = client.post("/api/art/bank/units", headers=admin, json={
        "donor_id": donor_id, "sample_code": "STRAW-1", "tank": "B1", "canister": "1", "cane": "A", "position": "2",
    })
    assert unit.status_code == 200, unit.text
    unit_id = unit.json()["id"]

    woman = _patient(client, admin, "Rhea", "9000000031")
    case = client.post("/api/art/cases", headers=admin, json={"case_type": "single_woman", "woman_patient_id": woman})
    case_id = case.json()["id"]
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "ivf", "billing_mode": "itemised",
    })
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]

    issued = client.post(f"/api/art/bank/units/{unit_id}/issue", headers=admin, json={
        "destination": "internal",
        "case_id": case_id,
        "cycle_id": cycle_id,
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert issued.status_code == 200, issued.text
    assert issued.json()["donor_code"] == code
    assert "legal_name" not in issued.json()
    chart = client.get(f"/api/art/cycles/{cycle_id}", headers=desk)
    assert chart.json()["donor_code"] == code
    assert "Private Donor" not in chart.text

    again = client.post(f"/api/art/bank/units/{unit_id}/issue", headers=admin, json={
        "destination": "internal", "case_id": case_id, "cycle_id": cycle_id,
        "operator_id": seed_data["admin_user_id"], "witness_id": seed_data["doctor_user_id"],
    })
    assert again.status_code == 400

    # A stored straw already tied to one case cannot be issued to another.
    from app.models.art import ArtBankUnit
    second = client.post("/api/art/bank/units", headers=admin, json={
        "donor_id": donor_id, "sample_code": "STRAW-2",
    })
    other_woman = _patient(client, admin, "Sana", "9000000032")
    other_case = client.post("/api/art/cases", headers=admin, json={
        "case_type": "single_woman", "woman_patient_id": other_woman,
    })
    other_cycle = client.post(f"/api/art/cases/{other_case.json()['id']}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    })
    row = db_session.query(ArtBankUnit).filter(ArtBankUnit.id == second.json()["id"]).one()
    row.case_id = case_id
    db_session.commit()
    stolen = client.post(f"/api/art/bank/units/{second.json()['id']}/issue", headers=admin, json={
        "destination": "internal",
        "case_id": other_case.json()["id"],
        "cycle_id": other_cycle.json()["id"],
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert stolen.status_code == 400

    partner = client.post("/api/art/partner-banks", headers=admin, json={
        "name": "City ART Bank", "registration_no": "EXT-1", "city": "Pune",
    })
    assert partner.status_code == 200, partner.text
    received = client.post("/api/art/bank/receive", headers=admin, json={
        "partner_bank_id": partner.json()["id"],
        "donor_code": "EXT-DON-7",
        "sample_code": "EXT-STRAW",
        "sample_type": "sperm",
        "case_id": case_id,
        "cycle_id": cycle_id,
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert received.status_code == 200, received.text
    assert received.json()["donor_code"] == "EXT-DON-7"
    outside = client.get(f"/api/art/cycles/{cycle_id}", headers=desk)
    assert outside.json()["donor_code"] == "EXT-DON-7"

    sperm = client.post("/api/art/donors", headers=admin, json={
        "donor_type": "sperm", "legal_name": "Sperm Donor", "phone": "9000000088",
    })
    client.post(f"/api/art/donors/{sperm.json()['id']}/screening", headers=admin, json={
        "hiv": "non_reactive", "hbsag": "non_reactive", "hcv": "non_reactive", "vdrl": "non_reactive",
    })
    assert client.post(f"/api/art/donors/{sperm.json()['id']}/clear", headers=admin).status_code == 200
    outbound = client.post("/api/art/bank/units", headers=admin, json={
        "donor_id": sperm.json()["id"], "sample_code": "OUT-1",
    })
    sent = client.post(f"/api/art/bank/units/{outbound.json()['id']}/issue", headers=admin, json={
        "destination": "external",
        "external_clinic_name": "Registered Clinic North",
        "operator_id": seed_data["admin_user_id"],
        "witness_id": seed_data["doctor_user_id"],
    })
    assert sent.status_code == 200, sent.text
    assert sent.json()["external_clinic_name"] == "Registered Clinic North"

    today = date.today()
    report = client.get(f"/api/art/registry?year={today.year}&month={today.month}", headers=admin)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["clinic"]["enrolments"] >= 1
    assert body["bank"]["donors_cleared"] >= 1
    assert body["bank"]["samples_issued"] >= 1
    assert body["bank"]["samples_received"] >= 1
    csv_res = client.get(
        f"/api/art/registry?year={today.year}&month={today.month}&format=csv", headers=admin,
    )
    assert csv_res.status_code == 200
    assert "enrolments" in csv_res.text


def test_phase4_outcomes_kpis_equipment_grievance(client, seed_data, db_session):
    admin = _headers("testadmin")
    client.put("/api/art/centre", headers=admin, json={"clinic_level": 2, "bank_enabled": True})
    woman = _patient(client, admin, "Meera", "9000000041", "1980-01-01")
    case = client.post("/api/art/cases", headers=admin, json={
        "case_type": "single_woman", "woman_patient_id": woman,
    })
    cycle = client.post(f"/api/art/cases/{case.json()['id']}/cycles", headers=admin, json={
        "cycle_type": "ivf",
        "protocol": "antagonist",
        "billing_mode": "itemised",
        "clinician_id": seed_data["doctor_user_id"],
    })
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]
    from app.models.art import ArtCycle
    db_session.query(ArtCycle).filter(ArtCycle.culture_open == True).update({"culture_open": False})  # noqa: E712
    db_session.commit()
    witness = {"witness_id": seed_data["doctor_user_id"]}
    for form in ("oocyte_retrieval", "couple_treatment"):
        client.post(f"/api/art/cases/{case.json()['id']}/consents", headers=admin, json={
            "form_code": form, "signed_by_name": "Meera Fertility",
        })
    assert client.post(f"/api/art/cycles/{cycle_id}/trigger", headers=admin, json={
        "drug": "hCG", "trigger_at": datetime.now().isoformat(),
    }).status_code == 200
    assert client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json={
        **witness, "follicles_aspirated": 12, "oocytes_retrieved": 10, "mature_mii": 9,
    }).status_code == 200
    fert = client.post(f"/api/art/cycles/{cycle_id}/fertilisation", headers=admin, json={
        "method": "ivf",
        "oocytes_inseminated": 10,
        "normally_fertilised": 7,
        "operator_id": seed_data["admin_user_id"],
        **witness,
    })
    assert fert.status_code == 200, fert.text
    early = client.post(f"/api/art/cycles/{cycle_id}/outcome", headers=admin, json={"clinical_pregnancy": True})
    assert early.status_code == 400
    assert client.post(f"/api/art/cycles/{cycle_id}/culture/open", headers=admin).status_code == 200
    embryo = client.post(f"/api/art/cycles/{cycle_id}/specimens", headers=admin, json={"sample_type": "embryo"})
    assert embryo.status_code == 200, embryo.text
    moved = client.post(f"/api/art/specimens/{embryo.json()['id']}/dispose", headers=admin, json={
        **witness, "disposition": "transfer",
    })
    assert moved.status_code == 200, moved.text
    outcome = client.post(f"/api/art/cycles/{cycle_id}/outcome", headers=admin, json={
        "beta_hcg_value": 240,
        "beta_hcg_positive": True,
        "clinical_pregnancy": True,
        "miscarriage": False,
        "live_birth": False,
        "complication": "Mild OHSS",
    })
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["clinical_pregnancy"] is True

    report = client.get("/api/art/reports/outcomes", headers=admin)
    assert report.status_code == 200, report.text
    by_type = report.json()["by_cycle_type"]["ivf"]
    assert by_type["clinical_pregnancies"] >= 1
    assert by_type["clinical_pregnancy_rate"] > 0
    assert "38-40" in report.json()["by_age"] or "41+" in report.json()["by_age"]

    kpis = client.get("/api/art/reports/lab-kpis", headers=admin)
    assert kpis.status_code == 200, kpis.text
    assert kpis.json()["fertilisation_rate"] is not None
    assert kpis.json()["normally_fertilised"] >= 7

    equip = client.post("/api/art/equipment", headers=admin, json={
        "name": "CO2 incubator", "asset_code": "INC-1", "installed_on": "2024-01-01", "status": "active",
    })
    assert equip.status_code == 200, equip.text
    changed = client.patch(f"/api/art/equipment/{equip.json()['id']}", headers=admin, json={
        "name": "CO2 incubator",
        "asset_code": "INC-1",
        "status": "active",
        "last_change_on": date.today().isoformat(),
        "change_note": "Replaced sensor",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["change_note"] == "Replaced sensor"

    opened = client.post("/api/art/grievances", headers=admin, json={
        "complainant_name": "Rhea Fertility",
        "summary": "Waiting time on scan day",
    })
    assert opened.status_code == 200, opened.text
    closed = client.post(f"/api/art/grievances/{opened.json()['id']}/close", headers=admin, json={
        "resolution": "Scan slot moved earlier",
    })
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"

    today = date.today()
    registry = client.get(f"/api/art/registry?year={today.year}&month={today.month}", headers=admin)
    complications = registry.json()["clinic"]["complications"]
    assert any(item["complication"] == "Mild OHSS" for item in complications)
