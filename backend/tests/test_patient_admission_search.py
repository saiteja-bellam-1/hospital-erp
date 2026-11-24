"""Pharmacy POS patient search also matches inpatient admission number and id."""
import uuid

from app.models.inpatient import Admission, RoomManagement
from app.models.patient import Patient


def _admission_number():
    day = f"{uuid.uuid4().int % 10000:04d}"
    seq = f"{uuid.uuid4().int % 10000:04d}"
    return f"ADM-2099{day}-{seq}"


def _admit(db, seed_data, *, first_name, admission_number, status="admitted"):
    patient = Patient(
        patient_id=str(uuid.uuid4()),
        first_name=first_name,
        last_name="Stay",
        gender="female",
        primary_phone="6000000002",
        hospital_id=seed_data["hospital_id"],
    )
    room = RoomManagement(
        room_number=f"SR-{uuid.uuid4().hex[:6]}",
        room_type="general",
        floor="1",
        department="Ward",
        bed_count=1,
        available_beds=1,
        room_charge_per_day=100.0,
        hospital_id=seed_data["hospital_id"],
        is_active=True,
    )
    db.add(patient)
    db.add(room)
    db.flush()
    admission = Admission(
        admission_number=admission_number,
        patient_id=patient.id,
        admitting_doctor_id=seed_data["doctor_user_id"],
        room_id=room.id,
        bed_number="1",
        admission_type="elective",
        status=status,
    )
    db.add(admission)
    db.commit()
    db.refresh(admission)
    db.refresh(patient)
    return patient, admission


def _search(client, auth_headers, term, include_admissions=False):
    body = {"search_term": term, "sort_by": "name", "sort_order": "asc"}
    if include_admissions:
        body["include_admissions"] = True
    res = client.post("/api/patients/search", headers=auth_headers, json=body)
    assert res.status_code == 200, res.text
    return res.json().get("patients") or []


def test_pos_search_finds_patient_by_admission_number_and_id(
    client, auth_headers, seed_data, db_session,
):
    number = _admission_number()
    patient, admission = _admit(
        db_session, seed_data, first_name="AdmitSearch", admission_number=number,
    )

    by_number = _search(client, auth_headers, number, include_admissions=True)
    assert [p["id"] for p in by_number] == [patient.id]
    assert by_number[0]["admission_number"] == number
    assert by_number[0]["admission_id"] == admission.id
    assert by_number[0]["admission_status"] == "admitted"

    by_lower = _search(client, auth_headers, number.lower(), include_admissions=True)
    assert [p["id"] for p in by_lower] == [patient.id]

    by_id = _search(client, auth_headers, str(admission.id), include_admissions=True)
    assert any(p["id"] == patient.id and p["admission_id"] == admission.id for p in by_id)

    # Sequence fragment (last 4 of a standard ADM-YYYYMMDD-NNNN) still matches.
    sequence = number.split("-")[-1]
    assert len(sequence) == 4
    by_seq = _search(client, auth_headers, sequence, include_admissions=True)
    assert any(p["id"] == patient.id for p in by_seq)

    # Other screens keep the old search: the admission number is not a name or phone.
    assert _search(client, auth_headers, number, include_admissions=False) == []

    # A short digit string must not hit every admission whose date contains those digits.
    if admission.id != 15:
        short = _search(client, auth_headers, "15", include_admissions=True)
        assert all(p["id"] != patient.id for p in short)


def test_name_search_shows_active_admission_only(
    client, auth_headers, seed_data, db_session,
):
    active_no = _admission_number()
    old_no = _admission_number()
    active_patient, active = _admit(
        db_session, seed_data, first_name="ActiveStay", admission_number=active_no,
    )
    discharged_patient, _old = _admit(
        db_session, seed_data, first_name="OldStay", admission_number=old_no, status="discharged",
    )

    named = _search(client, auth_headers, "ActiveStay", include_admissions=True)
    match = next(p for p in named if p["id"] == active_patient.id)
    assert match["admission_number"] == active_no
    assert match["admission_id"] == active.id

    old_named = _search(client, auth_headers, "OldStay", include_admissions=True)
    old_match = next(p for p in old_named if p["id"] == discharged_patient.id)
    assert old_match.get("admission_number") in (None, "")

    # The discharged stay is still findable by its own admission number.
    by_old = _search(client, auth_headers, old_no, include_admissions=True)
    assert [p["id"] for p in by_old] == [discharged_patient.id]
    assert by_old[0]["admission_number"] == old_no
    assert by_old[0]["admission_status"] == "discharged"
