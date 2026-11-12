"""14-day machine trial: clock, login, module grant, and license override.

The store is pointed at a temp folder so these tests never write HKLM or
ProgramData on the machine running pytest.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.license import License
from app.services.license_service import (
    get_license_status,
    is_license_valid_for_login,
    license_allows_customisation,
    license_denies_module,
)
from app.services.trial import (
    STATUS_TRIAL,
    STATUS_TRIAL_EXPIRED,
    TRIAL_FEATURES,
    clear_isolated_store,
    set_now,
    trial_begin,
    trial_status,
    use_isolated_store,
)


T0 = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture
def trial_clock(tmp_path):
    clock = {"now": T0}

    def _set(when: datetime) -> None:
        clock["now"] = when

    use_isolated_store(str(tmp_path / "trial-store"), fingerprint="pc-1")
    set_now(lambda: clock["now"])
    clock["set"] = _set
    try:
        yield clock
    finally:
        clear_isolated_store()


@pytest.fixture
def empty_license_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'trial.db'}",
        connect_args={"check_same_thread": False},
    )
    License.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _enabled_modules(db_path: str) -> dict:
    from app.models.system import SystemModule

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        return {row.module_name: row.is_enabled for row in db.query(SystemModule).all()}
    finally:
        db.close()
        engine.dispose()


def test_reinstall_does_not_reset_the_clock(trial_clock):
    first = trial_begin()
    assert first["ok"] is True
    assert first["created"] is True
    assert first["status"] == STATUS_TRIAL
    assert first["days_remaining"] == 14
    started = first["started_at"]
    expires = first["expires_at"]

    trial_clock["set"](T0 + timedelta(days=3))
    second = trial_begin()
    assert second["created"] is False
    assert second["started_at"] == started
    assert second["expires_at"] == expires
    assert second["status"] == STATUS_TRIAL
    assert second["days_remaining"] == 11

    trial_clock["set"](T0 + timedelta(days=20))
    third = trial_begin()
    assert third["created"] is False
    assert third["started_at"] == started
    assert third["expires_at"] == expires
    assert third["status"] == STATUS_TRIAL_EXPIRED
    assert third["days_remaining"] == 0


def test_clock_rollback_does_not_extend_the_trial(trial_clock):
    first = trial_begin()
    expires = first["expires_at"]

    trial_clock["set"](T0 + timedelta(days=10))
    seen = trial_status(touch=True)
    assert seen["status"] == STATUS_TRIAL
    assert seen["expires_at"] == expires

    trial_clock["set"](T0 + timedelta(days=1))
    rolled = trial_status(touch=True)
    assert rolled["expires_at"] == expires
    assert rolled["started_at"] == first["started_at"]
    assert rolled["status"] == STATUS_TRIAL
    assert rolled["days_remaining"] == 4


def test_active_trial_lets_staff_in_and_licenses_product_modules(trial_clock, empty_license_db):
    trial_begin()
    db = empty_license_db

    allowed, reason = is_license_valid_for_login(db, "receptionist")
    assert allowed is True
    assert reason == ""

    status = get_license_status(db)
    assert status["status"] == STATUS_TRIAL
    assert status["days_remaining"] == 14
    assert set(status["features"]) == set(TRIAL_FEATURES)
    assert "customisation" not in status["features"]
    assert "whatsapp" not in status["features"]
    assert license_allows_customisation(db) is False
    for name in ("outpatient", "inpatient", "lab", "pharmacy", "physiotherapy", "ehr"):
        assert license_denies_module(db, name) is False


def test_expired_trial_blocks_staff_and_allows_admin(trial_clock, empty_license_db):
    trial_begin()
    trial_clock["set"](T0 + timedelta(days=15))
    db = empty_license_db

    staff_ok, staff_reason = is_license_valid_for_login(db, "receptionist")
    assert staff_ok is False
    assert "trial" in staff_reason.lower()

    admin_ok, admin_reason = is_license_valid_for_login(db, "hospital_admin")
    assert admin_ok is True
    assert admin_reason == ""

    status = get_license_status(db)
    assert status["status"] == STATUS_TRIAL_EXPIRED
    assert status["days_remaining"] == 0


def test_paid_license_overrides_an_active_trial(trial_clock, empty_license_db):
    trial_begin()
    db = empty_license_db
    db.add(License(
        license_id="LIC-OVERRIDE",
        hospital_id="HOSP01",
        hospital_name="City Hospital",
        plan="standard",
        max_users=25,
        features=["outpatient"],
        issued_at=T0 - timedelta(days=1),
        expires_at=T0 + timedelta(days=400),
        status="active",
        raw_license_data="",
    ))
    db.commit()

    status = get_license_status(db)
    assert status["status"] == "active"
    assert status["plan"] == "standard"
    assert status["features"] == ["outpatient"]
    assert license_denies_module(db, "inpatient") is True
    assert license_denies_module(db, "outpatient") is False

    allowed, _reason = is_license_valid_for_login(db, "receptionist")
    assert allowed is True


def test_fresh_seed_enables_modules_only_while_the_trial_is_active(trial_clock, tmp_path):
    from app.services.db_seed import init_database_and_seed

    seed = {
        "hospital_name": "Trial Hospital",
        "admin_username": "trialadmin",
        "admin_email": "trialadmin@local",
        "admin_password": "trial-pass-1",
    }

    trial_begin()
    active_path = str(tmp_path / "active.db")
    init_database_and_seed(seed, active_path)
    active = _enabled_modules(active_path)
    for name in ("outpatient", "inpatient", "lab", "pharmacy", "physiotherapy", "ehr", "billing", "admin"):
        assert active[name] is True

    trial_clock["set"](T0 + timedelta(days=20))
    expired_path = str(tmp_path / "expired.db")
    init_database_and_seed(seed, expired_path)
    expired = _enabled_modules(expired_path)
    assert expired["inpatient"] is False
    assert expired["lab"] is False
    assert expired["pharmacy"] is False
    assert expired["physiotherapy"] is False
    assert expired["billing"] is True
    assert expired["admin"] is True
