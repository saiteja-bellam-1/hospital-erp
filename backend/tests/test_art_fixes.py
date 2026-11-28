"""Regression tests for the ART review fixes.

Each test names the review item it covers.
"""
import os
import uuid
from datetime import date, timedelta

from app.models.art import ArtDocument, ArtSpecimen, ArtCycle, ArtCentre
from app.models.hospital import Hospital
from app.models.user import User
from app.services.db_seed import _ART_CLINICIAN, _ART_COUNSELLOR, _ART_EMBRYOLOGIST
from tests.test_art_module import _doctor_can_witness, _headers, _patient, _user  # noqa: F401


import pytest


@pytest.fixture(autouse=True)
def _release_benches(db_session):
    yield
    _close_benches(db_session)


def _lab_centre(client, admin):
    res = client.put("/api/art/centre", headers=admin, json={"clinic_level": 2, "bank_enabled": True})
    assert res.status_code == 200, res.text


def _couple(client, admin, first, phone):
    woman = _patient(client, admin, first, phone, "1990-02-02")
    partner = _patient(client, admin, "Arun", f"{phone[:-1]}9")
    res = client.post("/api/art/cases", headers=admin, json={
        "case_type": "couple", "woman_patient_id": woman, "partner_patient_id": partner,
    })
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _consent(client, admin, case_id, form):
    res = client.post(f"/api/art/cases/{case_id}/consents", headers=admin, json={
        "form_code": form, "signed_by_name": "Signer",
    })
    assert res.status_code == 200, res.text


def _close_benches(db_session):
    """Tests share one DB; clear cultures earlier tests left open."""
    db_session.query(ArtCycle).filter(ArtCycle.culture_open == True).update({"culture_open": False})  # noqa: E712
    db_session.commit()


def _embryo_cycle(client, admin, seed_data, case_id, embryos=2, db_session=None):
    """IVF cycle with open culture and N embryos in the incubator."""
    if db_session is not None:
        _close_benches(db_session)
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "ivf", "billing_mode": "itemised",
    })
    assert cycle.status_code == 200, cycle.text
    cycle_id = cycle.json()["id"]
    _consent(client, admin, case_id, "oocyte_retrieval")
    assert client.post(f"/api/art/cycles/{cycle_id}/trigger", headers=admin, json={
        "drug": "hCG", "trigger_at": "2026-01-01T08:00:00",
    }).status_code == 200
    got = client.post(f"/api/art/cycles/{cycle_id}/retrieval", headers=admin, json=_witnessed(
        seed_data, oocytes_retrieved=embryos + 2, mature_mii=embryos + 2,
    ))
    assert got.status_code == 200, got.text
    fert = client.post(f"/api/art/cycles/{cycle_id}/fertilisation", headers=admin, json=_witnessed(
        seed_data, method="icsi", oocytes_inseminated=embryos + 2, normally_fertilised=embryos,
    ))
    assert fert.status_code == 200, fert.text
    assert client.post(f"/api/art/cycles/{cycle_id}/culture/open", headers=admin).status_code == 200
    ids = []
    for _ in range(embryos):
        res = client.post(f"/api/art/cycles/{cycle_id}/specimens", headers=admin, json={"sample_type": "embryo"})
        assert res.status_code == 200, res.text
        ids.append(res.json()["id"])
    return cycle_id, ids


def _witnessed(seed_data, **extra):
    return {"witness_id": seed_data["doctor_user_id"], **extra}


def _freeze(client, admin, seed_data, specimen_id, position="1"):
    res = client.post(f"/api/art/specimens/{specimen_id}/dispose", headers=admin, json=_witnessed(
        seed_data, disposition="freeze", tank="T1", canister="C1", cane="N1", position=position,
    ))
    assert res.status_code == 200, res.text


# B1 — saving clinic setup must not wipe fields the form did not send.
def test_centre_update_keeps_unsent_validity_dates(client, seed_data, db_session):
    admin = _headers("testadmin")
    until = (date.today() + timedelta(days=365)).isoformat()
    res = client.put("/api/art/centre", headers=admin, json={
        "clinic_level": 1, "clinic_valid_until": until, "bank_valid_until": until,
    })
    assert res.status_code == 200, res.text
    again = client.put("/api/art/centre", headers=admin, json={"clinic_level": 1, "director_name": "Dr A"})
    assert again.status_code == 200, again.text
    assert again.json()["clinic_valid_until"] == until
    assert again.json()["bank_valid_until"] == until
    assert again.json()["director_name"] == "Dr A"


# B2 — overdue renewals stay on the board and are flagged.
def test_board_shows_overdue_renewals(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Pooja", "9100000011")
    _consent(client, admin, case_id, "embryo_freeze")
    _, (embryo, _) = _embryo_cycle(client, admin, seed_data, case_id, db_session=db_session)
    _freeze(client, admin, seed_data, embryo)
    row = db_session.query(ArtSpecimen).filter(ArtSpecimen.id == embryo).one()
    row.renewal_due = date.today() - timedelta(days=10)
    db_session.commit()
    board = client.get("/api/art/board", headers=admin).json()
    hit = next(item for item in board["cryo_renewals"] if item["code"] == row.code)
    assert hit["overdue"] is True


# B3 — thaw several embryos into one FET cycle; transfer moves the FET cycle.
def test_fet_thaw_into_one_cycle_and_transfer(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Sneha", "9100000021")
    for form in ("embryo_freeze", "couple_treatment"):
        _consent(client, admin, case_id, form)
    origin_id, (first, second) = _embryo_cycle(client, admin, seed_data, case_id, db_session=db_session)
    _freeze(client, admin, seed_data, first, "1")
    _freeze(client, admin, seed_data, second, "2")
    client.post(f"/api/art/cycles/{origin_id}/culture/close", headers=admin)

    # A frozen embryo cannot go straight to transfer.
    frozen_transfer = client.post(f"/api/art/specimens/{first}/dispose", headers=admin, json=_witnessed(
        seed_data, disposition="transfer",
    ))
    assert frozen_transfer.status_code == 400
    assert "thaw" in frozen_transfer.json()["detail"].lower()

    one = client.post(f"/api/art/specimens/{first}/thaw", headers=admin, json=_witnessed(seed_data))
    assert one.status_code == 200, one.text
    fet_id = one.json()["cycle_id"]
    two = client.post(f"/api/art/specimens/{second}/thaw", headers=admin, json=_witnessed(
        seed_data, into_cycle_id=fet_id, survived=False,
    ))
    assert two.status_code == 200, two.text
    assert two.json()["cycle_id"] == fet_id
    assert db_session.query(ArtCycle).filter(ArtCycle.case_id == case_id, ArtCycle.cycle_type == "fet").count() == 1

    # Grading after the thaw uses the FET cycle's culture.
    closed = client.post(f"/api/art/specimens/{first}/grade", headers=admin, json={"day": 5, "grade": "4AA"})
    assert closed.status_code == 400
    assert client.post(f"/api/art/cycles/{fet_id}/culture/open", headers=admin).status_code == 200
    graded = client.post(f"/api/art/specimens/{first}/grade", headers=admin, json={"day": 5, "grade": "4AA"})
    assert graded.status_code == 200, graded.text

    dead = client.post(f"/api/art/specimens/{second}/dispose", headers=admin, json=_witnessed(
        seed_data, disposition="transfer",
    ))
    assert dead.status_code == 400
    assert "survive" in dead.json()["detail"].lower()

    moved = client.post(f"/api/art/specimens/{first}/dispose", headers=admin, json=_witnessed(
        seed_data, disposition="transfer",
    ))
    assert moved.status_code == 200, moved.text
    db_session.expire_all()
    assert db_session.query(ArtCycle).get(fet_id).status == "transfer"
    assert db_session.query(ArtCycle).get(origin_id).status != "transfer"


def test_thaw_into_another_case_cycle_is_refused(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_a = _couple(client, admin, "Uma", "9100000031")
    case_b = _couple(client, admin, "Vani", "9100000041")
    _consent(client, admin, case_a, "embryo_freeze")
    _, (embryo,) = _embryo_cycle(client, admin, seed_data, case_a, embryos=1, db_session=db_session)
    _freeze(client, admin, seed_data, embryo)
    other = client.post(f"/api/art/cases/{case_b}/cycles", headers=admin, json={
        "cycle_type": "fet", "billing_mode": "itemised",
    })
    res = client.post(f"/api/art/specimens/{embryo}/thaw", headers=admin, json=_witnessed(
        seed_data, into_cycle_id=other.json()["id"],
    ))
    assert res.status_code == 400
    assert db_session.query(ArtSpecimen).get(embryo).disposition == "frozen"


# B4 — witnesses must be real, active, same-hospital staff with the permission;
# the operator is the signed-in user.
def test_witness_and_operator_rules(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Wafa", "9100000051")
    _consent(client, admin, case_id, "embryo_freeze")
    _, (embryo,) = _embryo_cycle(client, admin, seed_data, case_id, embryos=1, db_session=db_session)

    other_hospital = Hospital(hospital_id=str(uuid.uuid4()), name="Elsewhere", address="x", phone="1", email="x@y.z")
    db_session.add(other_hospital)
    db_session.flush()
    outsider = _user(db_session, other_hospital.id, "artoutsider", "art_embryologist", _ART_EMBRYOLOGIST)
    inactive = _user(db_session, seed_data["hospital_id"], "artinactive", "art_embryologist", _ART_EMBRYOLOGIST)
    inactive.is_active = False
    counsellor = _user(db_session, seed_data["hospital_id"], "artcounsel", "art_counsellor", _ART_COUNSELLOR)
    db_session.commit()

    def freeze(**body):
        return client.post(f"/api/art/specimens/{embryo}/dispose", headers=admin, json={
            "disposition": "freeze", "tank": "T1", "canister": "C1", "cane": "N1", "position": "9", **body,
        })

    assert freeze(witness_id=outsider.id).status_code == 404
    assert freeze(witness_id=inactive.id).status_code == 400
    no_perm = freeze(witness_id=counsellor.id)
    assert no_perm.status_code == 403
    assert "witness" in no_perm.json()["detail"].lower()
    spoofed = freeze(witness_id=seed_data["doctor_user_id"], operator_id=counsellor.id)
    assert spoofed.status_code == 400
    assert "signed in" in spoofed.json()["detail"]
    assert freeze(witness_id=seed_data["admin_user_id"]).status_code == 400  # self-witness
    assert freeze(witness_id=seed_data["doctor_user_id"]).status_code == 200


def test_timeout_checks_name_and_witness(client, seed_data, db_session):
    admin = _headers("testadmin")
    client.put("/api/art/centre", headers=admin, json={"clinic_level": 1})
    case_id = _couple(client, admin, "Yamini", "9100000061")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "iui_husband", "billing_mode": "itemised",
    }).json()["id"]
    _consent(client, admin, case_id, "iui_husband")
    appt = client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "cycle_id": cycle, "kind": "iui", "scheduled_date": date.today().isoformat(),
    }).json()["id"]
    url = f"/api/art/appointments/{appt}/timeout"
    wrong = client.post(url, headers=admin, json={
        "patient_name": "Someone Else", "dob_confirmed": True, "witness_id": seed_data["doctor_user_id"],
    })
    assert wrong.status_code == 400
    assert "does not match" in wrong.json()["detail"]
    self_witness = client.post(url, headers=admin, json={
        "patient_name": "Yamini Fertility", "dob_confirmed": True, "witness_id": seed_data["admin_user_id"],
    })
    assert self_witness.status_code == 400
    ok = client.post(url, headers=admin, json={
        "patient_name": "yamini fertility", "dob_confirmed": True, "witness_id": seed_data["doctor_user_id"],
    })
    assert ok.status_code == 200, ok.text


# B5 — withdraw_consent and collect_advance are enforced.
def test_withdrawal_and_advance_permissions(client, seed_data, db_session):
    admin = _headers("testadmin")
    client.put("/api/art/centre", headers=admin, json={"clinic_level": 1})
    counsellor = _headers(_user(db_session, seed_data["hospital_id"], "artcounsel", "art_counsellor", _ART_COUNSELLOR).username)
    clinician = _headers(_user(db_session, seed_data["hospital_id"], "artclin", "art_clinician", _ART_CLINICIAN).username)
    case_id = _couple(client, admin, "Zara", "9100000071")
    _consent(client, admin, case_id, "couple_treatment")

    blocked = client.post(f"/api/art/cases/{case_id}/consents", headers=counsellor, json={
        "form_code": "withdrawal", "signed_by_name": "Zara",
    })
    assert blocked.status_code == 403
    consent_id = client.get(f"/api/art/cases/{case_id}", headers=admin).json()["consents"][0]["id"]
    assert client.post(f"/api/art/consents/{consent_id}/withdraw", headers=counsellor).status_code == 403
    single = client.post(f"/api/art/consents/{consent_id}/withdraw", headers=clinician)
    assert single.status_code == 200, single.text
    assert client.post(f"/api/art/consents/{consent_id}/withdraw", headers=clinician).status_code == 400

    pkg = client.post("/api/art/packages", headers=admin, json={"name": "P", "price": 1000}).json()["id"]
    no_collect = client.post(f"/api/art/cases/{case_id}/cycles", headers=clinician, json={
        "cycle_type": "oi", "billing_mode": "package", "package_template_id": pkg, "collect_advance": True,
    })
    assert no_collect.status_code == 403
    assert "collect_advance" in no_collect.json()["detail"]
    later = client.post(f"/api/art/cases/{case_id}/cycles", headers=clinician, json={
        "cycle_type": "oi", "billing_mode": "package", "package_template_id": pkg, "collect_advance": False,
    })
    assert later.status_code == 200, later.text


# B8 — upload filenames cannot escape the folder; type and size are checked.
def test_upload_is_sanitised(client, seed_data, db_session):
    from app.utils.paths import get_uploads_dir
    admin = _headers("testadmin")
    case_id = _couple(client, admin, "Asha", "9100000081")
    res = client.post(
        f"/api/art/cases/{case_id}/documents", headers=admin,
        data={"document_name": "Scan"},
        files={"file": ("../../../evil.txt", b"x", "text/plain")},
    )
    assert res.status_code == 200, res.text
    row = db_session.query(ArtDocument).get(res.json()["id"])
    assert row.file_name == "evil.txt"
    folder = os.path.realpath(os.path.join(get_uploads_dir(), "art_docs"))
    stored = os.path.realpath(os.path.join(get_uploads_dir(), row.file_path))
    assert os.path.dirname(stored) == folder
    assert os.path.isfile(stored)

    bad_type = client.post(
        f"/api/art/cases/{case_id}/documents", headers=admin,
        data={"document_name": "Exe"}, files={"file": ("run.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad_type.status_code == 400
    too_big = client.post(
        f"/api/art/cases/{case_id}/documents", headers=admin,
        data={"document_name": "Big"}, files={"file": ("big.pdf", b"0" * (10 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert too_big.status_code == 400


def _bills(client, admin, cycle_id):
    res = client.get(f"/api/art/cycles/{cycle_id}/bills", headers=admin)
    assert res.status_code == 200, res.text
    return res.json()


def _single(client, admin, first, phone):
    woman = _patient(client, admin, first, phone)
    res = client.post("/api/art/cases", headers=admin, json={"case_type": "single_woman", "woman_patient_id": woman})
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _scan_package(client, admin, price=20000, keep=2000):
    client.post("/api/art/services", headers=admin, json={"code": "FXSCAN", "name": "Scan", "default_price": 1000})
    res = client.post("/api/art/packages", headers=admin, json={
        "name": f"Scan pack {price}", "price": price, "included_service_codes": ["FXSCAN"], "cancel_keep_amount": keep,
    })
    assert res.status_code == 200, res.text
    return res.json()["id"]


# B6 — cancelling settles every bill on the cycle.
def test_cancel_with_unpaid_advance_voids_it(client, seed_data, db_session):
    admin = _headers("testadmin")
    pkg = _scan_package(client, admin)
    case_id = _single(client, admin, "Bina", "9100000091")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "package", "package_template_id": pkg, "collect_advance": False,
    }).json()
    extra = client.post(f"/api/art/cycles/{cycle['id']}/charges", headers=admin, json={
        "description": "Outside test", "amount": 700,
    })
    assert extra.json()["bill_id"]
    res = client.post(f"/api/art/cycles/{cycle['id']}/cancel", headers=admin, json={"reason": "Changed mind"})
    assert res.status_code == 200, res.text
    assert res.json()["refund_bill_id"] is None
    statuses = {b["id"]: b["status"] for b in _bills(client, admin, cycle["id"])}
    assert statuses[cycle["advance_bill_id"]] == "cancelled"
    assert statuses[extra.json()["bill_id"]] == "cancelled"


def test_cancel_partly_paid_advance_waives_balance_and_refunds_with_payment(client, seed_data, db_session):
    from app.models.billing import Bill, Payment
    admin = _headers("testadmin")
    pkg = _scan_package(client, admin, price=20000, keep=2000)
    case_id = _single(client, admin, "Charu", "9100000101")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "package", "package_template_id": pkg, "collect_advance": False,
    }).json()
    paid = client.post(f"/api/art/bills/{cycle['advance_bill_id']}/payments", headers=admin, json={"amount": 12000})
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "partial"
    over = client.post(f"/api/art/bills/{cycle['advance_bill_id']}/payments", headers=admin, json={"amount": 9000})
    assert over.status_code == 400

    res = client.post(f"/api/art/cycles/{cycle['id']}/cancel", headers=admin, json={"reason": "Moved city"})
    assert res.status_code == 200, res.text
    db_session.expire_all()
    advance = db_session.query(Bill).get(cycle["advance_bill_id"])
    assert advance.status == "paid"
    assert advance.total_amount == 12000
    assert advance.discount_amount == 8000
    credit = db_session.query(Bill).get(res.json()["refund_bill_id"])
    assert credit.total_amount == -10000
    refund = db_session.query(Payment).filter(Payment.bill_id == credit.id).one()
    assert refund.amount_paid == -10000
    assert refund.payment_number.startswith("RFD-")
    assert refund.parent_payment_id is not None
    # Net cash kept equals the kept amount.
    cash = sum(p.amount_paid for p in db_session.query(Payment).filter(Payment.bill_id.in_([advance.id, credit.id])))
    assert cash == 2000


# B7 — switching billing modes moves the money.
def test_billing_mode_round_trip_moves_bills(client, seed_data, db_session):
    admin = _headers("testadmin")
    pkg = _scan_package(client, admin, price=15000)
    case_id = _single(client, admin, "Dimple", "9100000111")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "package", "package_template_id": pkg, "collect_advance": False,
    }).json()
    covered = client.post(f"/api/art/cycles/{cycle['id']}/charges", headers=admin, json={"service_code": "FXSCAN"})
    assert covered.json()["covered_by_package"] is True

    same = client.post(f"/api/art/cycles/{cycle['id']}/billing-mode", headers=admin, json={
        "billing_mode": "package", "reason": "x", "package_template_id": pkg,
    })
    assert same.status_code == 400

    to_item = client.post(f"/api/art/cycles/{cycle['id']}/billing-mode", headers=admin, json={
        "billing_mode": "itemised", "reason": "Patient prefers per visit",
    })
    assert to_item.status_code == 200, to_item.text
    assert to_item.json()["advance_bill_id"] is None
    bills = _bills(client, admin, cycle["id"])
    assert {b["id"]: b["status"] for b in bills}[cycle["advance_bill_id"]] == "cancelled"
    scan_bills = [b for b in bills if b["status"] == "pending" and b["total_amount"] == 1000]
    assert len(scan_bills) == 1
    assert to_item.json()["estimate_snapshot"]["billing_mode"] == "package"

    back = client.post(f"/api/art/cycles/{cycle['id']}/billing-mode", headers=admin, json={
        "billing_mode": "package", "reason": "Back to package", "package_template_id": pkg, "agreed_price": 14000,
    })
    assert back.status_code == 200, back.text
    assert back.json()["agreed_price"] == 14000
    bills = {b["id"]: b for b in _bills(client, admin, cycle["id"])}
    assert bills[scan_bills[0]["id"]]["status"] == "cancelled"
    new_advance = bills[back.json()["advance_bill_id"]]
    assert new_advance["total_amount"] == 14000 and new_advance["status"] == "pending"
    detail = client.get(f"/api/art/cycles/{cycle['id']}", headers=admin).json()
    assert all(c["covered_by_package"] for c in detail["charges"])


def test_inactive_package_cannot_be_switched_to(client, seed_data, db_session):
    from app.models.art import ArtPackageTemplate
    admin = _headers("testadmin")
    pkg = _scan_package(client, admin, price=9000)
    db_session.query(ArtPackageTemplate).filter(ArtPackageTemplate.id == pkg).update({"is_active": False})
    db_session.commit()
    case_id = _single(client, admin, "Esha", "9100000121")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    }).json()
    res = client.post(f"/api/art/cycles/{cycle['id']}/billing-mode", headers=admin, json={
        "billing_mode": "package", "reason": "x", "package_template_id": pkg,
    })
    assert res.status_code == 404


# B11 — cycle order, counts, and allowed types.
def test_cycle_type_and_appointment_kind_are_checked(client, seed_data, db_session):
    admin = _headers("testadmin")
    client.put("/api/art/centre", headers=admin, json={"clinic_level": 2})
    case_id = _couple(client, admin, "Gita", "9100000131")
    assert client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "magic", "billing_mode": "itemised",
    }).status_code == 400
    oi = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    }).json()["id"]
    today = date.today().isoformat()
    assert client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "kind": "party", "scheduled_date": today,
    }).status_code == 400
    opu_on_oi = client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "cycle_id": oi, "kind": "opu", "scheduled_date": today,
    })
    assert opu_on_oi.status_code == 400
    assert client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "kind": "transfer", "scheduled_date": today,
    }).status_code == 400
    scan = client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "cycle_id": oi, "kind": "scan", "scheduled_date": today,
    })
    assert scan.status_code == 200, scan.text


def test_stimulation_and_lab_order_and_counts(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    _close_benches(db_session)
    case_id = _couple(client, admin, "Hema", "9100000141")
    _consent(client, admin, case_id, "oocyte_retrieval")
    cycle_id = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "icsi", "billing_mode": "itemised",
    }).json()["id"]
    base = f"/api/art/cycles/{cycle_id}"
    assert client.post(f"{base}/stimulation", headers=admin, json={"day_number": 2}).status_code == 200
    dup = client.post(f"{base}/stimulation", headers=admin, json={"day_number": 2})
    assert dup.status_code == 400
    assert client.post(f"{base}/fertilisation", headers=admin, json=_witnessed(
        seed_data, method="icsi", oocytes_inseminated=1,
    )).status_code == 400  # before retrieval
    client.post(f"{base}/trigger", headers=admin, json={"drug": "hCG", "trigger_at": "2026-02-01T21:00:00"})
    too_many = client.post(f"{base}/retrieval", headers=admin, json=_witnessed(
        seed_data, follicles_aspirated=5, oocytes_retrieved=6,
    ))
    assert too_many.status_code == 400
    grades = client.post(f"{base}/retrieval", headers=admin, json=_witnessed(
        seed_data, oocytes_retrieved=6, mature_mii=5, intermediate_mi=1, immature_gv=1,
    ))
    assert grades.status_code == 400
    ok = client.post(f"{base}/retrieval", headers=admin, json=_witnessed(
        seed_data, follicles_aspirated=9, oocytes_retrieved=6, mature_mii=4, intermediate_mi=1, immature_gv=1,
    ))
    assert ok.status_code == 200, ok.text
    assert client.post(f"{base}/retrieval", headers=admin, json=_witnessed(
        seed_data, oocytes_retrieved=6,
    )).status_code == 400  # already recorded
    assert client.post(f"{base}/stimulation", headers=admin, json={"day_number": 12}).status_code == 400
    assert client.post(f"{base}/trigger", headers=admin, json={
        "drug": "hCG", "trigger_at": "2026-02-02T21:00:00",
    }).status_code == 400
    icsi_over = client.post(f"{base}/fertilisation", headers=admin, json=_witnessed(
        seed_data, method="icsi", oocytes_inseminated=5, normally_fertilised=3,
    ))
    assert icsi_over.status_code == 400
    assert "mii" in icsi_over.json()["detail"].lower()
    assert client.post(f"{base}/fertilisation", headers=admin, json=_witnessed(
        seed_data, method="icsi", oocytes_inseminated=4, normally_fertilised=5,
    )).status_code == 400
    assert client.post(f"{base}/fertilisation", headers=admin, json=_witnessed(
        seed_data, method="icsi", oocytes_inseminated=4, normally_fertilised=1,
    )).status_code == 200
    client.post(f"{base}/culture/open", headers=admin)
    assert client.post(f"{base}/specimens", headers=admin, json={"sample_type": "embryo"}).status_code == 200
    capped = client.post(f"{base}/specimens", headers=admin, json={"sample_type": "embryo"})
    assert capped.status_code == 400
    db_session.expire_all()
    assert db_session.query(ArtCycle).get(cycle_id).status == "culture"


def test_transfer_appointment_and_staged_outcome(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Indu", "9100000151")
    _consent(client, admin, case_id, "couple_treatment")
    cycle_id, (embryo,) = _embryo_cycle(client, admin, seed_data, case_id, embryos=1, db_session=db_session)
    today = date.today().isoformat()
    appt = client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "cycle_id": cycle_id, "kind": "transfer", "scheduled_date": today,
    })
    assert appt.status_code == 200, appt.text
    appt_id = appt.json()["id"]
    client.post(f"/api/art/appointments/{appt_id}/timeout", headers=admin, json={
        "patient_name": "Indu Fertility", "dob_confirmed": True, "witness_id": seed_data["doctor_user_id"],
    })
    early = client.post(f"/api/art/appointments/{appt_id}/complete", headers=admin)
    assert early.status_code == 400
    assert "worksheet" in early.json()["detail"]
    client.post(f"/api/art/specimens/{embryo}/dispose", headers=admin, json=_witnessed(seed_data, disposition="transfer"))
    done = client.post(f"/api/art/appointments/{appt_id}/complete", headers=admin)
    assert done.status_code == 200, done.text
    assert client.post(f"/api/art/appointments/{appt_id}/complete", headers=admin).status_code == 400

    url = f"/api/art/cycles/{cycle_id}/outcome"
    bad = client.post(url, headers=admin, json={"beta_hcg_positive": False, "clinical_pregnancy": True})
    assert bad.status_code == 400
    first = client.post(url, headers=admin, json={"beta_hcg_value": 310, "beta_hcg_positive": True})
    assert first.status_code == 200, first.text
    no_birth = client.post(url, headers=admin, json={"live_birth": True})
    assert no_birth.status_code == 400
    second = client.post(url, headers=admin, json={"clinical_pregnancy": True})
    assert second.status_code == 200
    third = client.post(url, headers=admin, json={"live_birth": True})
    assert third.status_code == 200, third.text
    db_session.expire_all()
    row = db_session.query(ArtCycle).get(cycle_id)
    assert row.beta_hcg_value == 310 and row.clinical_pregnancy and row.live_birth
    assert client.post(f"/api/art/cycles/{cycle_id}/cancel", headers=admin, json={"reason": "x"}).status_code == 400


def test_freezing_cycle_has_no_pregnancy_outcome(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _single(client, admin, "Jaya", "9100000161")
    cycle_id = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oocyte_freeze", "billing_mode": "itemised",
    }).json()["id"]
    url = f"/api/art/cycles/{cycle_id}/outcome"
    assert client.post(url, headers=admin, json={"clinical_pregnancy": True}).status_code == 400
    assert client.post(url, headers=admin, json={"complication": "Mild OHSS"}).status_code == 200


# B9 — uploaded documents are listed on the case.
def test_case_lists_documents(client, seed_data, db_session):
    admin = _headers("testadmin")
    case_id = _single(client, admin, "Kala", "9100000171")
    up = client.post(
        f"/api/art/cases/{case_id}/documents", headers=admin,
        data={"document_name": "HSG report", "document_type": "report"},
        files={"file": ("hsg.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert up.status_code == 200, up.text
    listed = client.get(f"/api/art/cases/{case_id}/documents", headers=admin).json()
    assert [d["document_name"] for d in listed] == ["HSG report"]
    on_case = client.get(f"/api/art/cases/{case_id}", headers=admin).json()["documents"]
    assert on_case[0]["file_name"] == "hsg.pdf"


# B12 — a culture belongs to the embryologist who opened it.
def test_culture_held_by_one_embryologist(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Lila", "9100000181")
    cycle_id, _ = _embryo_cycle(client, admin, seed_data, case_id, embryos=1, db_session=db_session)
    second = _user(db_session, seed_data["hospital_id"], "artemb2", "art_embryologist", _ART_EMBRYOLOGIST)
    other = _headers(second.username)
    taken = client.post(f"/api/art/cycles/{cycle_id}/culture/open", headers=other)
    assert taken.status_code == 409
    assert "bench" in taken.json()["detail"]
    assert client.post(f"/api/art/cycles/{cycle_id}/culture/close", headers=other).status_code == 403
    assert client.post(f"/api/art/cycles/{cycle_id}/culture/close", headers=admin).status_code == 200
    assert client.post(f"/api/art/cycles/{cycle_id}/culture/open", headers=other).status_code == 200


def _cleared_sperm_donor(client, admin, name):
    donor = client.post("/api/art/donors", headers=admin, json={"donor_type": "sperm", "legal_name": name}).json()
    clean = {k: "non_reactive" for k in ("hiv", "hbsag", "hcv", "vdrl")}
    assert client.post(f"/api/art/donors/{donor['id']}/screening", headers=admin, json=clean).status_code == 200
    assert client.post(f"/api/art/donors/{donor['id']}/clear", headers=admin).status_code == 200
    return donor


# B10 — bank samples match the cycle; one donor, one recipient; outside samples are usable.
def test_bank_issue_matches_cycle_and_recipient(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    donor = _cleared_sperm_donor(client, admin, "Bank Donor A")
    first = client.post("/api/art/bank/units", headers=admin, json={"donor_id": donor["id"], "sample_code": "FX-S-1"})
    assert first.status_code == 200, first.text
    dup = client.post("/api/art/bank/units", headers=admin, json={"donor_id": donor["id"], "sample_code": "FX-S-1"})
    assert dup.status_code == 400
    second = client.post("/api/art/bank/units", headers=admin, json={"donor_id": donor["id"], "sample_code": "FX-S-2"})

    couple = _couple(client, admin, "Mala", "9100000191")
    husband_iui = client.post(f"/api/art/cases/{couple}/cycles", headers=admin, json={
        "cycle_type": "iui_husband", "billing_mode": "itemised",
    }).json()["id"]
    wrong = client.post(f"/api/art/bank/units/{first.json()['id']}/issue", headers=admin, json=_witnessed(
        seed_data, destination="internal", case_id=couple, cycle_id=husband_iui,
    ))
    assert wrong.status_code == 400
    assert "donor iui" in wrong.json()["detail"].lower()

    woman_a = _single(client, admin, "Neha", "9100000201")
    cycle_a = client.post(f"/api/art/cases/{woman_a}/cycles", headers=admin, json={
        "cycle_type": "iui_donor", "billing_mode": "itemised",
    }).json()["id"]
    ok = client.post(f"/api/art/bank/units/{first.json()['id']}/issue", headers=admin, json=_witnessed(
        seed_data, destination="internal", case_id=woman_a, cycle_id=cycle_a,
    ))
    assert ok.status_code == 200, ok.text
    woman_b = _single(client, admin, "Ojas", "9100000211")
    cycle_b = client.post(f"/api/art/cases/{woman_b}/cycles", headers=admin, json={
        "cycle_type": "iui_donor", "billing_mode": "itemised",
    }).json()["id"]
    second_couple = client.post(f"/api/art/bank/units/{second.json()['id']}/issue", headers=admin, json=_witnessed(
        seed_data, destination="internal", case_id=woman_b, cycle_id=cycle_b,
    ))
    assert second_couple.status_code == 400
    assert "one recipient" in second_couple.json()["detail"]

    # An outside sample received without a cycle is stored, then issued like any straw.
    partner = client.post("/api/art/partner-banks", headers=admin, json={"name": "North Bank"}).json()["id"]
    bad_partner = client.post("/api/art/bank/receive", headers=admin, json=_witnessed(
        seed_data, partner_bank_id=99999, donor_code="X", sample_code="EXT-FX-0", sample_type="sperm",
    ))
    assert bad_partner.status_code == 404
    stored = client.post("/api/art/bank/receive", headers=admin, json=_witnessed(
        seed_data, partner_bank_id=partner, donor_code="NB-77", sample_code="EXT-FX-1", sample_type="sperm",
        tank="B2", canister="1", cane="C", position="4",
    ))
    assert stored.status_code == 200, stored.text
    assert stored.json()["status"] == "stored"
    later = client.post(f"/api/art/bank/units/{stored.json()['id']}/issue", headers=admin, json=_witnessed(
        seed_data, destination="internal", case_id=woman_b, cycle_id=cycle_b,
    ))
    assert later.status_code == 200, later.text
    assert later.json()["donor_code"] == "NB-77"


# B13 — rates use treated cycles; registry counts lab records, not only bookings.
def test_rates_use_treated_cycles_and_registry_counts_lab(client, seed_data, db_session):
    from app.models.art import ArtCase
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Pari", "9100000221")
    _consent(client, admin, case_id, "couple_treatment")
    before = client.get(f"/api/art/registry?year={date.today().year}&month={date.today().month}", headers=admin).json()
    cycle_id, (embryo,) = _embryo_cycle(client, admin, seed_data, case_id, embryos=1, db_session=db_session)
    client.post(f"/api/art/specimens/{embryo}/dispose", headers=admin, json=_witnessed(seed_data, disposition="transfer"))
    client.post(f"/api/art/cycles/{cycle_id}/outcome", headers=admin, json={"beta_hcg_positive": False})
    # A second cycle on a new case that is cancelled before transfer.
    other = _couple(client, admin, "Rani", "9100000231")
    dropped = client.post(f"/api/art/cases/{other}/cycles", headers=admin, json={
        "cycle_type": "icsi", "billing_mode": "itemised", "protocol": "fx-proto",
    }).json()["id"]
    client.post(f"/api/art/cycles/{dropped}/cancel", headers=admin, json={"reason": "Poor response"})

    report = client.get("/api/art/reports/outcomes", headers=admin).json()
    proto = report["by_protocol"]["fx-proto"]
    assert proto["cycles_started"] == 1 and proto["cancelled"] == 1 and proto["treated"] == 0
    assert proto["clinical_pregnancy_rate"] is None
    assert "oocyte_freeze" not in report["by_cycle_type"]

    after = client.get(f"/api/art/registry?year={date.today().year}&month={date.today().month}", headers=admin).json()
    procs, old = after["clinic"]["procedures"], before["clinic"]["procedures"]
    assert procs["opu"] == old["opu"] + 1  # recorded in the lab, never booked
    assert procs["transfer"] == old["transfer"] + 1
    assert procs["embryos_transferred"] == old["embryos_transferred"] + 1
    assert db_session.query(ArtCase).count() >= 2


# B14 — donor re-check, case rules, numbering.
def test_cleared_donor_rechecked_when_screening_changes(client, seed_data, db_session):
    admin = _headers("testadmin")
    donor = _cleared_sperm_donor(client, admin, "Recheck Donor")
    bad = client.post(f"/api/art/donors/{donor['id']}/screening", headers=admin, json={
        "hiv": "maybe", "hbsag": "non_reactive", "hcv": "non_reactive", "vdrl": "non_reactive",
    })
    assert bad.status_code == 400
    flipped = client.post(f"/api/art/donors/{donor['id']}/screening", headers=admin, json={
        "hiv": "reactive", "hbsag": "non_reactive", "hcv": "non_reactive", "vdrl": "non_reactive",
    })
    assert flipped.status_code == 200
    assert flipped.json()["status"] == "screening"
    store = client.post("/api/art/bank/units", headers=admin, json={"donor_id": donor["id"], "sample_code": "FX-RC-1"})
    assert store.status_code == 400


def test_case_rules_and_numbers(client, seed_data, db_session):
    admin = _headers("testadmin")
    man = _patient(client, admin, "Arun", "9100000241")
    assert client.post("/api/art/cases", headers=admin, json={
        "case_type": "single_woman", "woman_patient_id": man,
    }).status_code == 400
    woman = _patient(client, admin, "Sita", "9100000251")
    other_woman = _patient(client, admin, "Tara", "9100000261")
    assert client.post("/api/art/cases", headers=admin, json={
        "case_type": "couple", "woman_patient_id": woman, "partner_patient_id": other_woman,
    }).status_code == 400
    assert client.post("/api/art/cases", headers=admin, json={
        "case_type": "couple", "woman_patient_id": woman, "partner_patient_id": woman,
    }).status_code == 400
    first = client.post("/api/art/cases", headers=admin, json={"case_type": "single_woman", "woman_patient_id": woman})
    assert first.status_code == 200
    again = client.post("/api/art/cases", headers=admin, json={"case_type": "single_woman", "woman_patient_id": woman})
    assert again.status_code == 400
    assert "open case" in again.json()["detail"]

    case_id = first.json()["id"]
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    }).json()
    blocked = client.post(f"/api/art/cases/{case_id}/status", headers=admin, json={"status": "closed"})
    assert blocked.status_code == 400
    client.post(f"/api/art/cycles/{cycle['id']}/cancel", headers=admin, json={"reason": "Stop"})
    closed = client.post(f"/api/art/cases/{case_id}/status", headers=admin, json={"status": "closed"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised",
    }).status_code == 400
    reopened = client.post("/api/art/cases", headers=admin, json={"case_type": "single_woman", "woman_patient_id": woman})
    assert reopened.status_code == 200
    assert client.post(f"/api/art/cases/{case_id}/status", headers=admin, json={"status": "open"}).status_code == 400

    # Numbers never reuse a placeholder and keep counting.
    a = first.json()["case_number"]
    b = reopened.json()["case_number"]
    assert not a.startswith("TMP-") and not b.startswith("TMP-")
    assert int(b.rsplit("-", 1)[-1]) > int(a.rsplit("-", 1)[-1])
    assert not cycle["cycle_number"].startswith("TMP-")
