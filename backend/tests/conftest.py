"""
Shared fixtures for inpatient smoke tests.

Strategy: override the DB dependency to use a temporary SQLite file so the tests
don't touch the real database but still exercise all the SQL that runs in prod
(some SQLAlchemy features behave differently with in-memory DBs, so we use a temp file).
"""

import os
import sys
import tempfile
import uuid
from datetime import date
import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.database import Base, get_db
from app.utils.auth import get_password_hash, create_access_token, Modules


@pytest.fixture(scope="session")
def db_engine():
    """Create a temporary SQLite database for the entire test session."""
    # Import ALL models so Base.metadata knows every table
    import app.models.hospital      # noqa: F401
    import app.models.user          # noqa: F401
    import app.models.patient       # noqa: F401
    import app.models.system        # noqa: F401
    import app.models.billing       # noqa: F401
    import app.models.inpatient     # noqa: F401
    import app.models.permissions   # noqa: F401
    import app.models.lab           # noqa: F401
    import app.models.pharmacy      # noqa: F401
    import app.models.ehr           # noqa: F401
    import app.models.doctor_availability  # noqa: F401
    import app.models.license       # noqa: F401
    import app.models.prescriptions_simple  # noqa: F401
    import app.models.audit         # noqa: F401
    import app.models.referral      # noqa: F401
    import app.models.outpatient    # noqa: F401
    import app.models.canteen       # noqa: F401

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(
        f"sqlite:///{tmp.name}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    os.unlink(tmp.name)


@pytest.fixture(scope="session")
def TestSessionLocal(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture()
def db_session(TestSessionLocal):
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def app(db_engine, TestSessionLocal):
    """Return the FastAPI app with the DB dependency overridden."""
    from main import app as _app

    def _override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    _app.dependency_overrides[get_db] = _override_get_db
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def seed_data(db_engine, TestSessionLocal):
    """Create a hospital, admin user, doctor user, and patient for the tests."""
    from app.models.hospital import Hospital
    from app.models.user import User, UserRole
    from app.models.patient import Patient
    from app.models.system import SystemModule

    session = TestSessionLocal()
    try:
        # Hospital
        hospital = Hospital(
            hospital_id=str(uuid.uuid4()),
            name="Test Hospital",
            address="123 Test St",
            phone="1234567890",
            email="test@hospital.com",
        )
        session.add(hospital)
        session.flush()

        # Roles — get-or-create so this fixture is safe to run after other
        # tests in the same session DB have already seeded these roles.
        admin_role = session.query(UserRole).filter_by(name="super_admin").first()
        if admin_role is None:
            admin_role = UserRole(name="super_admin", is_system_role=True)
            session.add(admin_role)
        doctor_role = session.query(UserRole).filter_by(name="doctor").first()
        if doctor_role is None:
            doctor_role = UserRole(name="doctor", is_system_role=True)
            session.add(doctor_role)
        session.flush()

        # Admin user
        admin_user = User(
            username="testadmin",
            password_hash=get_password_hash("admin123"),
            email="admin@test.com",
            first_name="Test",
            last_name="Admin",
            role_id=admin_role.id,
            hospital_id=hospital.id,
            is_active=True,
        )
        session.add(admin_user)
        session.flush()

        # Doctor user
        doctor_user = User(
            username="testdoctor",
            password_hash=get_password_hash("doctor123"),
            email="doctor@test.com",
            first_name="Dr",
            last_name="Smith",
            role_id=doctor_role.id,
            hospital_id=hospital.id,
            is_active=True,
        )
        session.add(doctor_user)
        session.flush()

        # Inpatient module (enabled)
        inpatient_mod = SystemModule(
            module_name="inpatient",
            display_name="Inpatient",
            description="Inpatient management",
            is_enabled=True,
            is_always_enabled=False,
        )
        session.add(inpatient_mod)

        # Patient
        patient = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="John",
            last_name="Doe",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            primary_phone="9876543210",
            hospital_id=hospital.id,
        )
        session.add(patient)
        session.flush()

        session.commit()

        data = {
            "hospital_id": hospital.id,
            "admin_user_id": admin_user.id,
            "doctor_user_id": doctor_user.id,
            "patient_id": patient.id,
        }
        yield data
    finally:
        session.close()


@pytest.fixture(scope="session")
def auth_headers(seed_data):
    """Return Authorization headers using a super_admin JWT."""
    token = create_access_token(data={"sub": "testadmin"})
    return {"Authorization": f"Bearer {token}"}
