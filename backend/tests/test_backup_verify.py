"""Unit tests for `app.utils.backup_verify`.

Covers:
  - Sidecar is written even when the source DB is missing (so consumers can
    rely on the file existing).
  - Healthy SQLite file → sha256, integrity=ok, ok=True.
  - Corrupt file (non-SQLite bytes) → ok=False, error mentions header.
  - Empty file → ok=False, error mentions empty.
"""
import json
import os
import sqlite3
import sys
import tempfile

# Make `app` importable when running pytest from repo root or from backend/.
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.utils.backup_verify import verify_backup_artifact, read_sidecar, SIDECAR_SUFFIX  # noqa: E402


def _make_db_with_users(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES ('alice')")
    conn.commit()
    conn.close()


def test_verify_healthy_db(tmp_path):
    db_path = str(tmp_path / "good.db")
    _make_db_with_users(db_path)
    result = verify_backup_artifact(db_path, full_check=True)
    assert result["ok"] is True
    assert result["integrity"] == "ok"
    assert result["sha256"]
    assert result["error"] is None
    sidecar = read_sidecar(db_path)
    assert sidecar is not None
    assert sidecar["ok"] is True
    assert os.path.isfile(db_path + SIDECAR_SUFFIX)


def test_verify_corrupt_non_sqlite(tmp_path):
    bad_path = str(tmp_path / "bad.db")
    with open(bad_path, "wb") as f:
        f.write(b"not a sqlite file at all")
    result = verify_backup_artifact(bad_path, full_check=True)
    assert result["ok"] is False
    assert result["error"] is not None
    assert "header mismatch" in result["error"] or "header" in result["error"].lower()


def test_verify_empty_file(tmp_path):
    empty_path = str(tmp_path / "empty.db")
    open(empty_path, "wb").close()
    result = verify_backup_artifact(empty_path, full_check=True)
    assert result["ok"] is False
    assert "empty" in (result["error"] or "").lower()


def test_verify_missing_file(tmp_path):
    missing_path = str(tmp_path / "missing.db")
    result = verify_backup_artifact(missing_path, full_check=True)
    assert result["ok"] is False
    # Sidecar should still exist so callers can rely on its presence.
    assert os.path.isfile(missing_path + SIDECAR_SUFFIX)


def test_verify_quick_check_path(tmp_path):
    db_path = str(tmp_path / "quick.db")
    _make_db_with_users(db_path)
    result = verify_backup_artifact(db_path, full_check=False)
    assert result["ok"] is True
    assert result["check_type"] == "quick_check"


def test_source_sha256_recorded(tmp_path):
    src = str(tmp_path / "src.db")
    dst = str(tmp_path / "dst.db")
    _make_db_with_users(src)
    # Bit-for-bit copy
    with open(src, "rb") as s, open(dst, "wb") as d:
        d.write(s.read())
    result = verify_backup_artifact(dst, full_check=True, source_db_path=src)
    assert result["ok"] is True
    assert result["sha256"] == result["source_sha256"]
