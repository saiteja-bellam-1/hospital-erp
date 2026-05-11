"""End-to-end pipeline tests for the backup feature.

These tests exercise the actual `run_backup`, `run_mirror_sync`, and
`run_snapshot` functions against a temp DB + temp backup location, then
walk through:

  - manual backup → sidecar present + verified ok
  - mirror → sidecar present + verified ok
  - snapshot folder → sidecar present + uploads bundled in folder
  - restore-verify probe on each artifact

We monkeypatch `get_configured_db_path`, `get_uploads_dir`, and
`load_config` so the production threads don't touch real install state.
"""
import os
import sqlite3
import sys
import datetime

import pytest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _seed_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('alice')")
    conn.commit()
    conn.close()


@pytest.fixture
def stub_install(tmp_path, monkeypatch):
    """Build a fake KT HEALTH ERP install rooted under tmp_path."""
    db_path = tmp_path / "kthealth_erp.db"
    uploads_dir = tmp_path / "uploads"
    backup_loc = tmp_path / "backup_target"
    uploads_dir.mkdir()
    backup_loc.mkdir()
    (uploads_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nlogo")
    _seed_db(str(db_path))

    from app.utils import config as cfg
    from app.utils import paths

    monkeypatch.setattr(cfg, "load_config", lambda: {
        "backup_locations": [str(backup_loc)],
        "snapshot_retention_days": 7,
    })
    monkeypatch.setattr(cfg, "get_configured_db_path", lambda: str(db_path))
    monkeypatch.setattr(paths, "get_uploads_dir", lambda: str(uploads_dir))
    # Reset module-level mirror tracking so each test starts clean.
    monkeypatch.setattr(cfg, "_per_location_mirror_status", {})

    return {
        "db_path": str(db_path),
        "uploads_dir": str(uploads_dir),
        "backup_loc": str(backup_loc),
    }


def test_manual_backup_writes_sidecar(stub_install):
    from app.utils.config import run_backup
    from app.utils.backup_verify import read_sidecar

    result = run_backup()
    assert result["success"], result
    assert result["results"][0]["verified"] is True

    location = stub_install["backup_loc"]
    candidates = [n for n in os.listdir(location) if n.startswith("kthealth_erp_backup_")]
    assert candidates, "manual backup folder missing"
    backup_dir = os.path.join(location, candidates[0])
    db_copy = os.path.join(backup_dir, "kthealth_erp.db")
    assert os.path.isfile(db_copy)
    sidecar = read_sidecar(db_copy)
    assert sidecar is not None
    assert sidecar["ok"] is True
    assert sidecar["integrity"] == "ok"
    # Uploads bundled
    assert os.path.isfile(os.path.join(backup_dir, "uploads", "logo.png"))


def test_mirror_writes_sidecar_and_uses_quick_check(stub_install):
    from app.utils.config import run_mirror_sync
    from app.utils.backup_verify import read_sidecar

    run_mirror_sync()
    mirror_db = os.path.join(stub_install["backup_loc"], "kthealth_erp_mirror", "kthealth_erp.db")
    assert os.path.isfile(mirror_db)
    sidecar = read_sidecar(mirror_db)
    assert sidecar is not None
    assert sidecar["ok"] is True
    assert sidecar["check_type"] == "quick_check"
    # Uploads mirrored
    assert os.path.isfile(os.path.join(stub_install["backup_loc"], "kthealth_erp_mirror", "uploads", "logo.png"))


def test_snapshot_includes_uploads(stub_install):
    from app.utils.config import run_snapshot, SNAPSHOT_FOLDER, get_snapshot_info
    from app.utils.backup_verify import read_sidecar

    run_snapshot()
    snap_root = os.path.join(stub_install["backup_loc"], SNAPSHOT_FOLDER)
    assert os.path.isdir(snap_root)
    entries = [e for e in os.listdir(snap_root) if e.startswith("snapshot_")]
    assert entries, "snapshot folder not created"
    snap_dir = os.path.join(snap_root, entries[0])
    assert os.path.isdir(snap_dir)
    db_copy = os.path.join(snap_dir, "kthealth_erp.db")
    assert os.path.isfile(db_copy)
    sidecar = read_sidecar(db_copy)
    assert sidecar and sidecar["ok"] is True
    assert sidecar["check_type"] == "integrity_check"
    # Uploads bundled with the snapshot — the Phase 1 fix.
    assert os.path.isfile(os.path.join(snap_dir, "uploads", "logo.png"))

    info = get_snapshot_info([stub_install["backup_loc"]])
    assert info["total_count"] >= 1
    most_recent = info["recent"][0]
    assert most_recent["verified"] is True
    assert most_recent["has_uploads"] is True


def test_snapshot_retention_days_resolution(stub_install):
    """Legacy `snapshot_retention_hours=72` should resolve to 3 days, and
    a fresh install with neither key should default to 7."""
    from app.utils.config import _resolve_snapshot_retention_days

    assert _resolve_snapshot_retention_days({"snapshot_retention_days": 14}) == 14
    assert _resolve_snapshot_retention_days({"snapshot_retention_hours": 72}) == 3
    assert _resolve_snapshot_retention_days({}) == 7
    # Sub-day legacy retention floors to 1, never zero.
    assert _resolve_snapshot_retention_days({"snapshot_retention_hours": 4}) == 1


def test_corrupt_destination_marked_unverified(stub_install, monkeypatch):
    """If a verification fails post-write, the manual backup result must
    report verified=False rather than declare success."""
    from app.utils import config as cfg
    from app.utils import backup_verify as bv

    original = bv.verify_backup_artifact

    def _fail_verify(*args, **kwargs):
        result = original(*args, **kwargs)
        # Pretend integrity_check returned a bad value, while still writing
        # the sidecar so consumers can read the failure detail.
        result["ok"] = False
        result["integrity"] = "malformed"
        result["error"] = "Simulated corruption"
        return result

    monkeypatch.setattr(bv, "verify_backup_artifact", _fail_verify)
    monkeypatch.setattr(cfg, "verify_backup_artifact", _fail_verify, raising=False)

    # Re-import inside config.run_backup picks the patched module reference.
    result = cfg.run_backup()
    assert result["results"][0]["verified"] is False
    assert "verification failed" in result["results"][0]["message"].lower()


def test_validate_backup_db_file_rejects_no_users(tmp_path):
    """The /restore validator must refuse a DB that's structurally fine but
    has no users (i.e. not actually a hospital DB)."""
    from app.routes.backup import _validate_backup_db_file
    import sqlite3
    from fastapi import HTTPException

    db = tmp_path / "empty_users.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc:
        _validate_backup_db_file(str(db), "/nonexistent/current.db", allow_same_path=True)
    assert "no users" in str(exc.value.detail).lower()
