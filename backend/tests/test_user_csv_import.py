"""Tests for app.services.user_csv_import.

Validator tests run pure-Python (no DB). Applier tests use the shared session
DB; they create + delete users in a UserRole-seeded hospital so they don't
pollute the session fixture's seed_data state.
"""
from __future__ import annotations

import pytest

from app.services.user_csv_import import (
    INSTALLER_ALLOWED_ROLES,
    apply_doctors,
    apply_nurses,
    apply_users,
    parse_and_validate,
    parse_and_validate_doctors,
    parse_and_validate_nurses,
)


# --------------------------------------------------------------------------- #
# parse_and_validate                                                          #
# --------------------------------------------------------------------------- #

HEADER = "username,email,first_name,last_name,role,password,phone,additional_roles\n"


def _err_messages(errors):
    return [e.message for e in errors]


def test_happy_path_parses_three_rows():
    csv = HEADER + (
        "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,9876543210,\n"
        "asha,asha@h.in,Asha,M,receptionist,Welcome@123,,inpatient_admin\n"
        "neha,neha@h.in,Neha,J,lab_technician,Welcome@123,,\n"
    )
    rows, errors = parse_and_validate(csv)
    assert errors == [], _err_messages(errors)
    assert len(rows) == 3
    assert rows[1].additional_roles == ["inpatient_admin"]


def test_missing_required_column_is_file_level_error():
    bad_header = "username,email,first_name,last_name,role\n"
    rows, errors = parse_and_validate(bad_header + "x,x@h.in,X,Y,receptionist\n")
    assert rows == []
    assert any("password" in e.message for e in errors)


def test_blank_csv_errors():
    _, errors = parse_and_validate("")
    assert any("empty" in e.message for e in errors)


def test_header_only_errors():
    _, errors = parse_and_validate(HEADER)
    assert any("no user rows" in e.message for e in errors)


def test_duplicate_username_within_file_blocks():
    csv = HEADER + (
        "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,\n"
        "ravi,ravi2@h.in,Ravi,J,receptionist,Welcome@123,,\n"
    )
    _, errors = parse_and_validate(csv)
    assert any("also appears on line" in e.message and e.field == "username" for e in errors)


def test_duplicate_email_within_file_blocks():
    csv = HEADER + (
        "ravi,shared@h.in,Ravi,K,billing_admin,Welcome@123,,\n"
        "asha,shared@h.in,Asha,M,receptionist,Welcome@123,,\n"
    )
    _, errors = parse_and_validate(csv)
    assert any("also appears on line" in e.message and e.field == "email" for e in errors)


def test_db_collision_username_blocks():
    csv = HEADER + "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,\n"
    _, errors = parse_and_validate(
        csv,
        existing_usernames=["ravi"],
        existing_emails=[],
    )
    assert any("already exists in the database" in e.message for e in errors)


def test_db_collision_email_blocks():
    csv = HEADER + "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,\n"
    _, errors = parse_and_validate(
        csv,
        existing_usernames=[],
        existing_emails=["ravi@h.in"],
    )
    assert any("already exists in the database" in e.message and e.field == "email" for e in errors)


@pytest.mark.parametrize("role", ["doctor", "nurse", "super_admin"])
def test_disallowed_roles_blocked(role):
    csv = HEADER + f"x,x@h.in,X,Y,{role},Welcome@123,,\n"
    _, errors = parse_and_validate(csv)
    assert any(e.field == "role" and "not allowed here" in e.message for e in errors)


def test_short_password_blocks():
    csv = HEADER + "ravi,ravi@h.in,Ravi,K,billing_admin,short,,\n"
    _, errors = parse_and_validate(csv)
    assert any(e.field == "password" and "at least" in e.message for e in errors)


def test_bad_email_blocks():
    csv = HEADER + "ravi,not-an-email,Ravi,K,billing_admin,Welcome@123,,\n"
    _, errors = parse_and_validate(csv)
    assert any(e.field == "email" and "not a valid email" in e.message for e in errors)


def test_additional_role_must_be_in_allowlist():
    csv = HEADER + "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,doctor\n"
    _, errors = parse_and_validate(csv)
    assert any(e.field == "additional_roles" and "not allowed" in e.message for e in errors)


def test_additional_role_cannot_duplicate_primary():
    csv = HEADER + "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,billing_admin\n"
    _, errors = parse_and_validate(csv)
    assert any(e.field == "additional_roles" and "duplicates the primary role" in e.message for e in errors)


def test_blank_lines_skipped():
    csv = HEADER + (
        "ravi,ravi@h.in,Ravi,K,billing_admin,Welcome@123,,\n"
        "\n"
        ",,,,,,,\n"
    )
    rows, errors = parse_and_validate(csv)
    # Both the literally-blank line AND the all-commas line are treated as
    # blank — operators routinely save CSVs with trailing empty rows.
    assert len(rows) == 1
    assert errors == []


# --------------------------------------------------------------------------- #
# apply_users                                                                 #
# --------------------------------------------------------------------------- #

@pytest.fixture
def csv_test_hospital(db_session):
    """Fresh hospital + seeded UserRole rows for the installer-allowed set."""
    import uuid
    from app.models.hospital import Hospital
    from app.models.user import UserRole

    hosp = Hospital(
        hospital_id=str(uuid.uuid4()),
        name="CSV Test Hospital",
        address="x",
        phone="1",
        email=f"csv-{uuid.uuid4().hex[:6]}@h.in",
    )
    db_session.add(hosp)
    db_session.flush()

    # Seed every role the CSV path can reference.
    for name in INSTALLER_ALLOWED_ROLES:
        if not db_session.query(UserRole).filter_by(name=name).first():
            db_session.add(UserRole(name=name, is_system_role=True))
    db_session.commit()

    yield hosp.id

    # Cleanup any users created by the test against this hospital.
    from app.models.user import User
    db_session.query(User).filter(User.hospital_id == hosp.id).delete()
    db_session.delete(hosp)
    db_session.commit()


def test_apply_users_creates_users_with_must_change_password(db_session, csv_test_hospital):
    from app.models.user import User
    from app.utils.auth import verify_password

    csv = HEADER + (
        "csvu1,csvu1@h.in,One,A,billing_admin,Welcome@123,9000000001,\n"
        "csvu2,csvu2@h.in,Two,B,receptionist,Welcome@123,,inpatient_admin;frontdesk\n"
    )
    rows, errors = parse_and_validate(csv)
    assert errors == []

    result = apply_users(db_session, rows, csv_test_hospital)
    assert result["created"] == 2

    u1 = db_session.query(User).filter_by(username="csvu1").one()
    assert u1.must_change_password is True
    assert u1.hospital_id == csv_test_hospital
    assert verify_password("Welcome@123", u1.password_hash)
    assert u1.role.name == "billing_admin"
    assert {r.name for r in u1.roles} == set()  # no extra roles

    u2 = db_session.query(User).filter_by(username="csvu2").one()
    assert u2.role.name == "receptionist"
    assert {r.name for r in u2.roles} == {"inpatient_admin", "frontdesk"}


def test_apply_users_blocks_on_runtime_db_conflict(db_session, csv_test_hospital):
    """Validator was called without DB context (e.g. dbcheck path) so it
    accepted the row; apply_users must still refuse when a live conflict
    appears."""
    import uuid
    from app.models.user import User, UserRole
    from app.utils.auth import get_password_hash

    # Pre-seed a colliding user.
    role = db_session.query(UserRole).filter_by(name="receptionist").one()
    db_session.add(User(
        user_id=str(uuid.uuid4()),
        username="csvclash",
        email="csvclash@h.in",
        password_hash=get_password_hash("Welcome@123"),
        first_name="X", last_name="Y",
        role_id=role.id, hospital_id=csv_test_hospital, is_active=True,
    ))
    db_session.commit()

    csv = HEADER + "csvclash,new@h.in,New,User,billing_admin,Welcome@123,,\n"
    rows, errors = parse_and_validate(csv)  # no DB context — passes
    assert errors == []

    with pytest.raises(ValueError, match="already exists"):
        apply_users(db_session, rows, csv_test_hospital)


# --------------------------------------------------------------------------- #
# Doctor importer                                                             #
# --------------------------------------------------------------------------- #

DOC_HEADER = (
    "username,email,first_name,last_name,password,phone,"
    "specialization,license_number,qualification,consultation_fee_inr,"
    "inpatient_fee_inr,emergency_fee_inr,experience_years,"
    "default_consultation_duration\n"
)


def test_doctor_parser_happy_path():
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,9000000001,"
        "Cardiology,MCI-12345,MBBS MD,800,2000,1500,12,15\n"
    )
    rows, errors = parse_and_validate_doctors(csv)
    assert errors == []
    assert rows[0].role == "doctor"
    assert rows[0].extras["specialization"] == "Cardiology"
    assert rows[0].extras["default_consultation_duration"] == "15"


def test_doctor_missing_specialization_blocks():
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,,,MCI-12345,,,,,,\n"
    )
    _, errors = parse_and_validate_doctors(csv)
    assert any(e.field == "specialization" for e in errors)


def test_doctor_missing_license_number_blocks():
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,,Cardiology,,,,,,,\n"
    )
    _, errors = parse_and_validate_doctors(csv)
    assert any(e.field == "license_number" for e in errors)


def test_doctor_invalid_duration_blocks():
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,,Cardio,MCI-1,,,,,,1\n"  # 1 < 2
    )
    _, errors = parse_and_validate_doctors(csv)
    assert any(e.field == "default_consultation_duration" for e in errors)


def test_doctor_non_numeric_fee_blocks():
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,,Cardio,MCI-1,,abc,,,,15\n"
    )
    _, errors = parse_and_validate_doctors(csv)
    assert any(e.field == "consultation_fee_inr" for e in errors)


def test_doctor_role_column_not_required():
    """Doctor importer pins role internally — operator does not need a role column."""
    csv = DOC_HEADER + (
        "drravi,drravi@h.in,Ravi,K,Welcome@123,,Cardio,MCI-1,,,,,,15\n"
    )
    rows, errors = parse_and_validate_doctors(csv)
    assert errors == []
    assert rows[0].role == "doctor"


def test_apply_doctors_creates_user_and_availability(db_session, csv_test_hospital):
    from app.models.user import User, UserRole
    from app.models.doctor_availability import DoctorAvailability
    from app.utils.auth import verify_password

    # csv_test_hospital fixture seeds installer roles but not 'doctor' — add it.
    if not db_session.query(UserRole).filter_by(name="doctor").first():
        db_session.add(UserRole(name="doctor", is_system_role=True))
        db_session.commit()

    csv = DOC_HEADER + (
        "drcsv,drcsv@h.in,CSV,Doctor,Welcome@123,9000000005,"
        "Cardiology,MCI-99,MBBS MD,800,2000,1500,12,20\n"
    )
    rows, errors = parse_and_validate_doctors(csv)
    assert errors == []

    result = apply_doctors(db_session, rows, csv_test_hospital)
    assert result["created"] == 1

    u = db_session.query(User).filter_by(username="drcsv").one()
    assert u.role.name == "doctor"
    assert u.specialization == "Cardiology"
    assert u.license_number == "MCI-99"
    assert u.must_change_password is True
    assert verify_password("Welcome@123", u.password_hash)

    avail = db_session.query(DoctorAvailability).filter_by(doctor_id=u.id).one()
    assert avail.default_consultation_duration == 20


# --------------------------------------------------------------------------- #
# Nurse importer                                                              #
# --------------------------------------------------------------------------- #

NURSE_HEADER = "username,email,first_name,last_name,password,phone\n"


def test_nurse_parser_happy_path():
    csv = NURSE_HEADER + (
        "ncsv,ncsv@h.in,CSV,Nurse,Welcome@123,9000000010\n"
    )
    rows, errors = parse_and_validate_nurses(csv)
    assert errors == []
    assert rows[0].role == "nurse"


def test_nurse_role_column_not_required():
    rows, errors = parse_and_validate_nurses(
        NURSE_HEADER + "ncsv,ncsv@h.in,CSV,Nurse,Welcome@123,\n"
    )
    assert errors == []
    assert rows[0].role == "nurse"


def test_apply_nurses_creates_users(db_session, csv_test_hospital):
    from app.models.user import User, UserRole

    if not db_session.query(UserRole).filter_by(name="nurse").first():
        db_session.add(UserRole(name="nurse", is_system_role=True))
        db_session.commit()

    csv = NURSE_HEADER + (
        "ncsv1,ncsv1@h.in,One,N,Welcome@123,9000000011\n"
        "ncsv2,ncsv2@h.in,Two,N,Welcome@123,\n"
    )
    rows, errors = parse_and_validate_nurses(csv)
    assert errors == []

    result = apply_nurses(db_session, rows, csv_test_hospital)
    assert result["created"] == 2

    for uname in ("ncsv1", "ncsv2"):
        u = db_session.query(User).filter_by(username=uname).one()
        assert u.role.name == "nurse"
        assert u.must_change_password is True
