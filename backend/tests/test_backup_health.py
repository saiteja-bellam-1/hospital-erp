"""Tests for `app.services.backup_health.compute_backup_health`.

We don't spin up the whole app; we monkey-patch the four functions
`compute_backup_health` calls into so we can simulate every state.
"""
import os
import sys
import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(THIS_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services import backup_health as bh  # noqa: E402


def _iso(seconds_ago: int) -> str:
    return (datetime.datetime.now() - datetime.timedelta(seconds=seconds_ago)).isoformat()


def _install(monkeypatch, *, locations=None, per_location=None,
             mirror=None, snapshot=None, gdrive=None, config=None):
    """Drop replacement implementations into app.utils.config so
    compute_backup_health() reads our fixtures."""
    from app.utils import config as cfg

    monkeypatch.setattr(cfg, "load_config", lambda: config or {"backup_locations": locations or []})
    monkeypatch.setattr(cfg, "get_per_location_status", lambda: per_location or {})
    monkeypatch.setattr(cfg, "get_mirror_status", lambda: mirror or {"running": False})
    monkeypatch.setattr(cfg, "get_snapshot_status", lambda: snapshot or {"running": False})
    monkeypatch.setattr(cfg, "get_gdrive_status", lambda: gdrive or {"enabled": False})


def test_no_locations_is_stale(monkeypatch):
    _install(monkeypatch, locations=[])
    out = bh.compute_backup_health()
    assert out["status"] == "stale"
    assert out["locations_configured"] == 0


def test_disabled_when_acknowledged(monkeypatch):
    _install(monkeypatch, locations=[], config={"backup_locations": [], "backup_disabled_acknowledged": True})
    out = bh.compute_backup_health()
    assert out["status"] == "disabled"


def test_healthy_single_location(monkeypatch):
    _install(
        monkeypatch,
        locations=["/tmp/back"],
        per_location={"/tmp/back": {"last_success": _iso(60), "last_error": None, "last_attempt": _iso(60), "writable": True}},
    )
    out = bh.compute_backup_health()
    assert out["status"] == "healthy"
    assert out["locations_healthy"] == 1
    assert out["broken"] == []


def test_stale_when_last_success_too_old(monkeypatch):
    _install(
        monkeypatch,
        locations=["/tmp/back"],
        per_location={"/tmp/back": {"last_success": _iso(60 * 60 * 24), "last_error": None, "last_attempt": _iso(60), "writable": True}},
    )
    out = bh.compute_backup_health()
    assert out["status"] == "stale"
    assert out["locations_healthy"] == 0


def test_broken_when_error_set(monkeypatch):
    _install(
        monkeypatch,
        locations=["/tmp/back"],
        per_location={"/tmp/back": {"last_success": None, "last_error": "PermissionError", "last_attempt": _iso(60), "writable": False}},
    )
    out = bh.compute_backup_health()
    assert out["status"] == "broken"
    assert len(out["broken"]) == 1
    assert out["broken"][0]["location"] == "/tmp/back"


def test_one_broken_one_healthy_is_broken(monkeypatch):
    _install(
        monkeypatch,
        locations=["/tmp/a", "/tmp/b"],
        per_location={
            "/tmp/a": {"last_success": _iso(60), "last_error": None, "last_attempt": _iso(60), "writable": True},
            "/tmp/b": {"last_success": None, "last_error": "disk full", "last_attempt": _iso(30), "writable": False},
        },
    )
    out = bh.compute_backup_health()
    # If any location is broken we promote to broken — partial-success is
    # not healthy from a data-safety standpoint.
    assert out["status"] == "broken"
    assert len(out["broken"]) == 1
