"""Tests for backup error log write/read used by the Backup page popup."""
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.utils import backup_log as blog  # noqa: E402


def test_log_backup_error_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(blog, "get_logs_dir", lambda: str(tmp_path))
    blog.log_backup_error("gdrive", "Token refresh failed: 400")
    out = blog.read_backup_errors()
    assert out["count"] == 1
    err = out["errors"][0]
    assert err["source"] == "gdrive"
    assert "Token refresh failed" in err["message"]
    assert os.path.isfile(out["path"])


def test_read_scans_server_log_for_backup_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(blog, "get_logs_dir", lambda: str(tmp_path))
    (tmp_path / "server.log").write_text(
        "info: started\n"
        "2026-08-18 06:48:00 [ERROR] uvicorn: Google Drive backup note: boom\n"
        "2026-08-18 06:49:00 [INFO] uvicorn: something else\n",
        encoding="utf-8",
    )
    out = blog.read_backup_errors()
    assert out["count"] == 1
    assert "boom" in out["errors"][0]["message"]


def test_empty_logs_returns_no_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(blog, "get_logs_dir", lambda: str(tmp_path))
    out = blog.read_backup_errors()
    assert out["count"] == 0
    assert out["errors"] == []


def test_dedupes_duplicate_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(blog, "get_logs_dir", lambda: str(tmp_path))
    blog.log_backup_error("mirror", "Permission denied")
    blog.log_backup_error("mirror", "Permission denied")
    out = blog.read_backup_errors()
    assert out["count"] == 1
