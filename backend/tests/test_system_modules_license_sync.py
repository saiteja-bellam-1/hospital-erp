"""System module catalog heal + license sync."""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config.database import Base

# Import models that participate in relationship() graphs so mapper configure succeeds.
import app.models.user  # noqa: F401
import app.models.doctor_availability  # noqa: F401
import app.models.hospital  # noqa: F401
from app.models.system import SystemModule
from app.services.system_modules import (
    CANONICAL_SYSTEM_MODULES,
    ensure_system_modules,
    sync_modules_with_license,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[SystemModule.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_pre_physio(db):
    """Customer DB as it existed before the physiotherapy release."""
    for mod_name, display, default_enabled, always_on in CANONICAL_SYSTEM_MODULES:
        if mod_name == "physiotherapy":
            continue
        db.add(
            SystemModule(
                module_name=mod_name,
                display_name=display,
                description=f"{display} management",
                is_enabled=True if always_on else default_enabled or mod_name in (
                    "outpatient", "lab", "inpatient", "pharmacy", "ehr",
                ),
                is_always_enabled=always_on,
            )
        )
    db.commit()


def test_ensure_creates_physio_enabled_when_licensed(db):
    _seed_pre_physio(db)
    assert db.query(SystemModule).filter_by(module_name="physiotherapy").first() is None

    created = ensure_system_modules(
        db,
        licensed_features=["outpatient", "lab", "ehr", "admin", "billing", "physiotherapy"],
    )
    db.commit()

    assert "physiotherapy" in created
    physio = db.query(SystemModule).filter_by(module_name="physiotherapy").one()
    assert physio.is_enabled is True
    assert physio.is_always_enabled is False


def test_ensure_creates_physio_disabled_without_license(db):
    _seed_pre_physio(db)
    created = ensure_system_modules(db, licensed_features=None)
    db.commit()
    assert "physiotherapy" in created
    physio = db.query(SystemModule).filter_by(module_name="physiotherapy").one()
    assert physio.is_enabled is False


def test_license_sync_inserts_and_enables_newly_licensed_physio(db):
    """Upgrade DB missing physio + renew license that adds physiotherapy."""
    _seed_pre_physio(db)
    previous = ["outpatient", "lab", "ehr", "admin", "billing", "inpatient", "pharmacy"]
    new_features = previous + ["physiotherapy"]

    sync_modules_with_license(db, new_features, previous_features=previous)

    physio = db.query(SystemModule).filter_by(module_name="physiotherapy").one()
    assert physio.is_enabled is True
    assert physio.display_name == "Physiotherapy"


def test_license_sync_does_not_reenable_admin_disabled_already_licensed(db):
    """Re-uploading a license must not flip modules an admin turned off."""
    _seed_pre_physio(db)
    db.add(
        SystemModule(
            module_name="physiotherapy",
            display_name="Physiotherapy",
            description="Physiotherapy management",
            is_enabled=False,
            is_always_enabled=False,
        )
    )
    db.commit()

    features = ["outpatient", "lab", "ehr", "admin", "billing", "physiotherapy"]
    sync_modules_with_license(db, features, previous_features=features)

    physio = db.query(SystemModule).filter_by(module_name="physiotherapy").one()
    assert physio.is_enabled is False


def test_license_sync_disables_dropped_features(db):
    _seed_pre_physio(db)
    inpatient = db.query(SystemModule).filter_by(module_name="inpatient").one()
    inpatient.is_enabled = True
    db.commit()

    sync_modules_with_license(
        db,
        ["outpatient", "lab", "ehr", "admin", "billing"],
        previous_features=["outpatient", "lab", "ehr", "admin", "billing", "inpatient"],
    )

    inpatient = db.query(SystemModule).filter_by(module_name="inpatient").one()
    assert inpatient.is_enabled is False
    # Always-on modules stay on even if omitted from features.
    admin = db.query(SystemModule).filter_by(module_name="admin").one()
    assert admin.is_enabled is True
