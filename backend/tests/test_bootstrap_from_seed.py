"""Tests for the installer-seed bootstrap.

These tests do not use the inpatient conftest fixtures because the bootstrap
needs to drive a *fresh* DB at a path the test owns — sharing the session-wide
test DB would defeat the point.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import pytest

# Ensure the backend package is importable when run from any directory.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def fake_install(tmp_path, monkeypatch):
    """Pretend the .exe lives at <tmp_path> with a sibling data/ directory.

    Patches app.utils.paths so config.json + DB land inside tmp_path. Each
    test gets its own tree so modules from one test don't leak into another.
    """
    exe_dir = tmp_path
    data_dir = exe_dir / "data"
    data_dir.mkdir()

    import app.utils.paths as paths
    monkeypatch.setattr(paths, "is_bundled", lambda: True)
    monkeypatch.setattr(paths, "get_base_dir", lambda: str(exe_dir))
    monkeypatch.setattr(paths, "get_data_dir", lambda: str(data_dir))
    monkeypatch.setattr(paths, "get_db_path", lambda: str(data_dir / "kthealth_erp.db"))
    monkeypatch.setattr(paths, "get_uploads_dir", lambda: str(data_dir / "uploads"))

    # app.utils.config does `from app.utils.paths import get_base_dir` so it
    # snapshots the function reference at import time. Patch the consumer
    # too, otherwise the first test's lambdas leak into subsequent tests.
    import app.utils.config as cfg
    monkeypatch.setattr(cfg, "is_bundled", lambda: True, raising=False)
    monkeypatch.setattr(cfg, "get_base_dir", lambda: str(exe_dir), raising=False)
    monkeypatch.setattr(cfg, "get_data_dir", lambda: str(data_dir), raising=False)

    yield exe_dir


def _write_seed(exe_dir, payload, password=None):
    seed = exe_dir / "data" / "install_seed.json"
    seed.write_text(json.dumps(payload))
    if password is not None:
        (exe_dir / "data" / ".install_seed.pwd").write_text(password)


def test_no_seed_returns_none(fake_install):
    from app.services.bootstrap_from_seed import consume_seed_if_present
    assert consume_seed_if_present(str(fake_install)) is None


def test_fresh_seed_creates_admin_and_hospital(fake_install):
    _write_seed(
        fake_install,
        {
            "mode": "fresh",
            "hospital_name": "Pytest Hospital",
            "admin_username": "pytestadmin",
            "admin_email": "pytest@local",
            "data_dir": str(fake_install / "data"),
            "backup_locations": [str(fake_install / "backup")],
        },
        password="StrongPass123",
    )

    from app.services.bootstrap_from_seed import consume_seed_if_present
    status = consume_seed_if_present(str(fake_install))

    assert status is not None
    assert status["applied"] is True
    assert status["mode"] == "fresh"

    # Seed files cleaned up
    data = fake_install / "data"
    assert not (data / "install_seed.json").exists()
    assert not (data / ".install_seed.pwd").exists()
    assert (data / ".bootstrap_status.json").exists()

    # DB has the admin user + hospital
    db = sqlite3.connect(str(data / "kthealth_erp.db"))
    try:
        users = db.execute("SELECT username, email FROM users").fetchall()
        hospitals = db.execute("SELECT name FROM hospitals").fetchall()
    finally:
        db.close()
    assert ("pytestadmin", "pytest@local") in users
    assert ("Pytest Hospital",) in hospitals

    # config.json reflects the chosen DB path + backup locations
    config = json.loads((fake_install / "config.json").read_text())
    assert config["setup_complete"] is True
    assert config["db_path"] == str(data / "kthealth_erp.db")
    assert config["backup_locations"] == [str(fake_install / "backup")]


def test_rerun_after_success_is_noop(fake_install):
    _write_seed(
        fake_install,
        {
            "mode": "fresh",
            "hospital_name": "Pytest Hospital",
            "admin_username": "rerunadmin",
            "data_dir": str(fake_install / "data"),
        },
        password="StrongPass123",
    )
    from app.services.bootstrap_from_seed import consume_seed_if_present
    assert consume_seed_if_present(str(fake_install))["applied"] is True
    # Second call: seed already consumed, nothing to apply.
    assert consume_seed_if_present(str(fake_install)) is None


def test_short_password_fails_and_preserves_seed(fake_install):
    _write_seed(
        fake_install,
        {
            "mode": "fresh",
            "hospital_name": "X",
            "admin_username": "a",
            "data_dir": str(fake_install / "data"),
        },
        password="short",
    )
    from app.services.bootstrap_from_seed import consume_seed_if_present
    status = consume_seed_if_present(str(fake_install))

    assert status["applied"] is False
    assert "password too short" in status["error"]
    # Seed kept so the operator can retry after fixing the password file.
    assert (fake_install / "data" / "install_seed.json").exists()
    assert (fake_install / "data" / ".install_seed.pwd").exists()


def test_adopt_existing_rebinds_config(fake_install):
    # First create an existing install in a different folder.
    existing = fake_install / "existing_data"
    existing.mkdir()
    # Copy the structure from a fresh-bootstrap into 'existing'.
    _write_seed(
        fake_install,
        {
            "mode": "fresh",
            "hospital_name": "Adopt Test",
            "admin_username": "adoptme",
            "data_dir": str(existing),
        },
        password="StrongPass123",
    )
    from app.services.bootstrap_from_seed import consume_seed_if_present
    consume_seed_if_present(str(fake_install))
    assert (existing / "kthealth_erp.db").exists()

    # Now: adopt scenario — operator points the wizard at the existing folder.
    _write_seed(
        fake_install,
        {
            "mode": "adopt_existing",
            "data_dir": str(existing),
            "backup_locations": [str(fake_install / "newbackup")],
        },
    )
    status = consume_seed_if_present(str(fake_install))
    assert status["applied"] is True
    assert status["mode"] == "adopt_existing"

    config = json.loads((fake_install / "config.json").read_text())
    assert config["db_path"] == str(existing / "kthealth_erp.db")
    assert config["backup_locations"] == [str(fake_install / "newbackup")]


def test_adopt_existing_missing_db_fails(fake_install):
    empty = fake_install / "empty"
    empty.mkdir()
    _write_seed(
        fake_install,
        {"mode": "adopt_existing", "data_dir": str(empty)},
    )
    from app.services.bootstrap_from_seed import consume_seed_if_present
    status = consume_seed_if_present(str(fake_install))
    assert status["applied"] is False
    assert "existing DB not found" in status["error"]


def test_unknown_mode_fails(fake_install):
    _write_seed(fake_install, {"mode": "wat"}, password="StrongPass123")
    from app.services.bootstrap_from_seed import consume_seed_if_present
    status = consume_seed_if_present(str(fake_install))
    assert status["applied"] is False
    assert "Unknown seed mode" in status["error"]
