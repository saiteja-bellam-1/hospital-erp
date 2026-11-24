"""Version selection and rollback rules for the in-app updater.

These tests stay off the network and off the live hospital database. They
cover which versions may be installed, and that a rollback copy restores the
database as it was when that version was left.
"""
import json
import os
import sqlite3

import pytest

from app.services import update_service as upd


def _db(path, name):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def _name(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT name FROM users").fetchone()[0]
    finally:
        conn.close()


def test_canonical_version_strips_prefix_and_prerelease():
    assert upd.canonical_version("v1.2.3") == "1.2.3"
    assert upd.canonical_version("1.2.3-beta+build") == "1.2.3"
    with pytest.raises(ValueError):
        upd.canonical_version("not-a-version")


def test_version_relation():
    assert upd.version_relation("1.3.0", "1.2.9") == "newer"
    assert upd.version_relation("1.2.0", "1.2.1") == "older"
    assert upd.version_relation("v1.2.1", "1.2.1") == "current"


def test_plan_apply_refuses_same_version():
    with pytest.raises(ValueError, match="already installed"):
        upd.plan_apply("1.2.2", "1.2.2", False, [])


def test_plan_apply_refuses_rollback_without_snapshot():
    with pytest.raises(ValueError, match="No saved database"):
        upd.plan_apply("1.2.2", "1.2.0", False, [])


def test_plan_apply_rollback_restores_snapshot():
    plan = upd.plan_apply("1.2.2", "1.2.0", False, ["1.2.0"])
    assert plan == {"relation": "older", "restore_snapshot": True, "version": "1.2.0"}


def test_plan_apply_upgrade_keeps_live_database_unless_asked():
    kept = upd.plan_apply("1.2.0", "1.2.2", False, ["1.2.2"])
    assert kept["relation"] == "newer"
    assert kept["restore_snapshot"] is False

    restored = upd.plan_apply("1.2.0", "1.2.2", True, ["1.2.2"])
    assert restored["restore_snapshot"] is True

    with pytest.raises(ValueError, match="No saved database"):
        upd.plan_apply("1.2.0", "1.2.2", True, [])


def test_snapshot_roundtrip_restores_saved_rows(tmp_path):
    live = str(tmp_path / "kthealth_erp.db")
    _db(live, "before")
    meta = upd.snapshot_database(live, str(tmp_path / "rollbacks"), "v1.2.0")
    assert meta["version"] == "1.2.0"
    assert os.path.isfile(tmp_path / "rollbacks" / "1.2.0" / "kthealth_erp.db")

    conn = sqlite3.connect(live)
    conn.execute("UPDATE users SET name = 'after'")
    conn.commit()
    conn.close()
    assert _name(live) == "after"

    snap = str(tmp_path / "rollbacks" / "1.2.0" / "kthealth_erp.db")
    upd.restore_database_file(snap, live)
    assert _name(live) == "before"


def test_prune_keeps_protected_oldest_version(tmp_path):
    root = tmp_path / "rollbacks"
    root.mkdir()
    for version, taken in (
        ("1.0.0", "2026-01-01T00:00:00"),
        ("1.1.0", "2026-02-01T00:00:00"),
        ("1.2.0", "2026-03-01T00:00:00"),
        ("1.3.0", "2026-04-01T00:00:00"),
    ):
        folder = root / version
        folder.mkdir()
        (folder / "kthealth_erp.db").write_bytes(b"x")
        (folder / "meta.json").write_text(json.dumps({"version": version, "taken_at": taken}))

    removed = upd.prune_snapshots(str(root), keep=2, protect={"1.0.0", "1.3.0"})
    assert "1.0.0" not in removed
    assert "1.3.0" not in removed
    assert os.path.isdir(root / "1.0.0")
    assert os.path.isdir(root / "1.3.0")
    assert not os.path.isdir(root / "1.1.0")


def test_public_release_hides_download_url_and_hash():
    entry = {
        "version": "1.2.0",
        "release_notes": "notes",
        "released_at": "2026-04-01",
        "mandatory": False,
        "prerelease": False,
        "installer_size": 10,
        "installer_url": "https://github.com/example/releases/download/v1.2.0/setup.exe",
        "installer_sha256": "abc",
    }
    public = upd.public_release(entry, "1.2.2", {
        "1.2.0": {"taken_at": "2026-03-01T00:00:00"},
    })
    assert public["relation"] == "older"
    assert public["snapshot_available"] is True
    assert "installer_url" not in public
    assert "installer_sha256" not in public


def test_newest_installable_skips_prerelease_and_current():
    entries = [
        {"version": "1.2.2", "prerelease": False},
        {"version": "1.3.0", "prerelease": True},
        {"version": "1.2.4", "prerelease": False},
    ]
    chosen = upd.newest_installable(entries, "1.2.2")
    assert chosen["version"] == "1.2.4"
    assert upd.newest_installable(entries, "1.2.4") is None


def test_dedupe_keeps_later_release_date():
    entries = [
        {"version": "v1.2.0", "released_at": "2026-01-01", "tag": "old"},
        {"version": "1.2.0", "released_at": "2026-06-01", "tag": "new"},
    ]
    kept = upd.dedupe_entries(entries)
    assert len(kept) == 1
    assert kept[0]["tag"] == "new"


def test_pending_restore_is_undone_when_the_program_did_not_change(tmp_path, monkeypatch):
    live = str(tmp_path / "kthealth_erp.db")
    _db(live, "original")
    upd.snapshot_database(live, str(tmp_path / "rollbacks"), "1.2.2")
    conn = sqlite3.connect(live)
    conn.execute("UPDATE users SET name = 'rolled-back'")
    conn.commit()
    conn.close()

    monkeypatch.setattr(upd, "get_state_dir", lambda: str(tmp_path))
    monkeypatch.setattr(upd, "get_current_version", lambda: "1.2.2")
    monkeypatch.setattr("app.utils.paths.get_db_path", lambda: live)
    upd.write_pending_restore("1.2.2", "1.2.0")

    note = upd.consume_pending_version_change()
    assert "put back" in note
    assert _name(live) == "original"
    assert not os.path.isfile(tmp_path / "rollbacks" / "pending.json")


def test_pending_restore_is_cleared_when_the_program_changed(tmp_path, monkeypatch):
    live = str(tmp_path / "kthealth_erp.db")
    _db(live, "kept")
    rollbacks = tmp_path / "rollbacks"
    rollbacks.mkdir()
    (rollbacks / "pending.json").write_text(json.dumps({
        "from_version": "1.2.0",
        "target_version": "1.2.2",
    }), encoding="utf-8")
    monkeypatch.setattr(upd, "get_state_dir", lambda: str(tmp_path))
    monkeypatch.setattr(upd, "get_current_version", lambda: "1.2.2")

    note = upd.consume_pending_version_change()
    assert "completed" in note
    assert _name(live) == "kept"
    assert not (rollbacks / "pending.json").is_file()


def test_entry_rejects_non_https_installer():
    with pytest.raises(ValueError, match="release host"):
        upd._entry_from_manifest(
            {
                "latest_version": "1.2.3",
                "installer_asset": "setup.exe",
                "installer_sha256": "aa",
            },
            "http://github.com/example/setup.exe",
            "v1.2.3",
            False,
        )


def test_start_download_refuses_rollback_without_snapshot(monkeypatch):
    entry = {
        "version": "1.0.0",
        "installer_asset": "setup.exe",
        "installer_sha256": "aa",
        "installer_size": 1,
        "installer_url": "https://github.com/example/repo/releases/download/v1.0.0/setup.exe",
    }
    monkeypatch.setattr(upd, "_lookup_version", lambda version: (entry, None))
    monkeypatch.setattr(upd, "get_current_version", lambda: "1.2.2")
    monkeypatch.setattr(upd, "list_snapshot_meta", lambda root=None: {})
    with upd._download_lock:
        upd._download_state["state"] = "idle"
    result = upd.start_download("1.0.0")
    assert result["started"] is False
    assert "No saved database" in result["reason"]
    with upd._download_lock:
        assert upd._download_state["state"] == "idle"
