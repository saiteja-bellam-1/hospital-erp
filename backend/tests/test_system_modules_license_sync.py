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


def _seed_missing_pharmacy(db):
    """Customer DB missing a toggleable catalog module (pharmacy)."""
    for mod_name, display, default_enabled, always_on in CANONICAL_SYSTEM_MODULES:
        if mod_name == "pharmacy":
            continue
        db.add(
            SystemModule(
                module_name=mod_name,
                display_name=display,
                description=f"{display} management",
                is_enabled=True if always_on else default_enabled,
                is_always_enabled=always_on,
            )
        )
    db.commit()


def test_ensure_creates_pharmacy_enabled_when_licensed(db):
    _seed_missing_pharmacy(db)
    assert db.query(SystemModule).filter_by(module_name="pharmacy").first() is None

    created = ensure_system_modules(
        db,
        licensed_features=["admin", "billing", "pharmacy"],
    )
    db.commit()

    assert "pharmacy" in created
    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is True
    assert pharmacy.is_always_enabled is False


def test_ensure_creates_pharmacy_disabled_without_license(db):
    _seed_missing_pharmacy(db)
    created = ensure_system_modules(db, licensed_features=None)
    db.commit()
    assert "pharmacy" in created
    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is False


def test_license_sync_inserts_and_enables_newly_licensed_pharmacy(db):
    """Upgrade DB missing pharmacy + renew license that adds pharmacy."""
    _seed_missing_pharmacy(db)
    previous = ["admin", "billing"]
    new_features = previous + ["pharmacy"]

    sync_modules_with_license(db, new_features, previous_features=previous)

    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is True
    assert pharmacy.display_name == "Pharmacy"


def test_license_sync_does_not_reenable_admin_disabled_already_licensed(db):
    """Re-uploading a license must not flip modules an admin turned off."""
    _seed_missing_pharmacy(db)
    db.add(
        SystemModule(
            module_name="pharmacy",
            display_name="Pharmacy",
            description="Pharmacy management",
            is_enabled=False,
            is_always_enabled=False,
        )
    )
    db.commit()

    features = ["admin", "billing", "pharmacy"]
    sync_modules_with_license(db, features, previous_features=features)

    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is False


def test_license_sync_disables_dropped_features(db):
    _seed_missing_pharmacy(db)
    ensure_system_modules(db, licensed_features=["admin", "billing", "pharmacy"])
    db.commit()

    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    pharmacy.is_enabled = True
    db.commit()

    sync_modules_with_license(
        db,
        ["admin", "billing"],
        previous_features=["admin", "billing", "pharmacy"],
    )

    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is False
    # Always-on modules stay on even if omitted from features.
    admin = db.query(SystemModule).filter_by(module_name="admin").one()
    assert admin.is_enabled is True


def test_post_upgrade_sync_enables_existing_disabled_licensed_module(db):
    """Software Update scenario: pharmacy row exists (disabled) + license already
    has pharmacy. Post-upgrade sync with previous_features=[] must enable it.
    """
    _seed_missing_pharmacy(db)
    db.add(
        SystemModule(
            module_name="pharmacy",
            display_name="Pharmacy",
            description="Pharmacy management",
            is_enabled=False,
            is_always_enabled=False,
        )
    )
    db.commit()

    features = [
        "admin", "billing", "pharmacy",
    ]
    sync_modules_with_license(db, features, previous_features=[])

    pharmacy = db.query(SystemModule).filter_by(module_name="pharmacy").one()
    assert pharmacy.is_enabled is True
