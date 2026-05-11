"""
Configuration manager for KT HEALTH ERP.
Reads/writes config.json which stores setup wizard choices.
"""
import json
import os
import shutil
import datetime
from app.utils.paths import get_data_dir, is_bundled, get_base_dir


CONFIG_FILENAME = "config.json"


def _get_config_path():
    """Get the path to config.json."""
    if is_bundled():
        return os.path.join(get_base_dir(), CONFIG_FILENAME)
    return os.path.join(get_base_dir(), CONFIG_FILENAME)


def load_config():
    """Load config from disk. Returns empty dict if not found."""
    path = _get_config_path()
    if os.path.isfile(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """Write config to disk."""
    path = _get_config_path()
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def is_setup_complete():
    """
    Check if the initial setup wizard has been completed.

    Truth chain (no backward-compat fallback):
      1. config.json must exist AND explicitly say setup_complete=True, AND
      2. the DB at the configured path must contain a usable users table
         with at least one row (sentinel-table probe).

    The pre-wizard "DB at default path → skip wizard" fallback was removed
    deliberately. Every install must run the wizard at least once so an
    operator either picks Fresh (creates an admin) or Restore (imports an
    existing DB) — the wizard is the single source of truth.
    """
    import sqlite3

    def _has_seeded_users(db_path: str) -> bool:
        if not db_path or not os.path.isfile(db_path) or os.path.getsize(db_path) == 0:
            return False
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                cur = conn.execute("SELECT 1 FROM users LIMIT 1")
                return cur.fetchone() is not None
            finally:
                conn.close()
        except Exception:
            return False

    config = load_config()
    if not config.get("setup_complete", False):
        return False

    from app.utils.paths import get_db_path
    db_path = config.get("db_path") or get_db_path()
    return _has_seeded_users(db_path)


def get_configured_db_path():
    """
    Get the DB path from config. Falls back to default if not configured.
    """
    config = load_config()
    custom_path = config.get("db_path", "")
    if custom_path and os.path.isdir(os.path.dirname(custom_path)):
        return custom_path
    # Default
    from app.utils.paths import get_db_path
    return get_db_path()


def get_backup_locations():
    """Get configured backup locations."""
    config = load_config()
    return config.get("backup_locations", [])


def run_backup():
    """
    Safely backup the SQLite database + uploads folder to all configured backup locations.
    Uses SQLite's built-in backup API to avoid corruption from active connections.
    Returns a dict with results for each location.
    """
    import sqlite3
    import shutil
    from app.utils.paths import get_uploads_dir

    config = load_config()
    db_path = get_configured_db_path()
    uploads_dir = get_uploads_dir()
    backup_locations = config.get("backup_locations", [])
    results = []

    if not os.path.isfile(db_path):
        return {"success": False, "error": "Database file not found", "results": []}

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder_name = f"kthealth_erp_backup_{timestamp}"
    backup_db_name = f"kthealth_erp.db"

    from app.utils.backup_verify import verify_backup_artifact

    for location in backup_locations:
        entry = {"path": location, "success": False, "message": "", "verified": False}
        try:
            backup_dir = os.path.join(location, backup_folder_name)
            os.makedirs(backup_dir, exist_ok=True)

            dest_db = os.path.join(backup_dir, backup_db_name)
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            if os.path.isdir(uploads_dir):
                dest_uploads = os.path.join(backup_dir, "uploads")
                shutil.copytree(uploads_dir, dest_uploads, dirs_exist_ok=True)

            # Verify the freshly-written backup before declaring success.
            verify = verify_backup_artifact(dest_db, full_check=True, source_db_path=db_path)
            entry["verified"] = verify["ok"]
            entry["integrity"] = verify["integrity"]
            entry["sha256"] = verify["sha256"]
            if not verify["ok"]:
                entry["success"] = False
                entry["message"] = f"Backup written but verification failed: {verify.get('error') or verify.get('integrity')}"
            else:
                entry["success"] = True
                entry["message"] = f"Backed up to {backup_dir}"
        except Exception as e:
            entry["message"] = str(e)
        results.append(entry)

    all_ok = all(r["success"] for r in results) if results else False
    return {
        "success": all_ok,
        "backup_file": backup_folder_name,
        "db_source": db_path,
        "results": results,
    }


# ============================================================
# Real-time Mirror Backup
# ============================================================

_mirror_thread = None
_mirror_running = False
_last_mirror_sync = None
_last_mirror_error = None


# Per-destination mirror status — tracks last success / last failure per
# location so the admin dashboard can show a green/red checklist instead of a
# single global flag (item 20 of installer overhaul).
_per_location_mirror_status: dict = {}


def run_mirror_sync():
    """
    Sync database + uploads to all backup locations as a live mirror.
    Overwrites the same files each time — no timestamped copies.
    Uses SQLite backup API for safe, consistent copies.
    """
    import sqlite3
    import shutil
    from app.utils.paths import get_uploads_dir
    global _last_mirror_sync, _last_mirror_error

    config = load_config()
    db_path = get_configured_db_path()
    uploads_dir = get_uploads_dir()
    backup_locations = config.get("backup_locations", [])

    if not os.path.isfile(db_path) or not backup_locations:
        return

    mirror_db_name = "kthealth_erp.db"
    from app.utils.backup_verify import verify_backup_artifact
    from app.services.backup_audit import record_location_transition

    for location in backup_locations:
        loc_status = _per_location_mirror_status.setdefault(location, {
            "last_success": None, "last_error": None, "last_attempt": None,
            "last_verified": None, "verified_sha256": None,
        })
        prev_state = "ok" if loc_status.get("last_success") and not loc_status.get("last_error") else ("error" if loc_status.get("last_error") else "new")
        loc_status["last_attempt"] = datetime.datetime.now().isoformat()
        try:
            mirror_dir = os.path.join(location, "kthealth_erp_mirror")
            os.makedirs(mirror_dir, exist_ok=True)

            dest_db = os.path.join(mirror_dir, mirror_db_name)
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            if os.path.isdir(uploads_dir):
                dest_uploads = os.path.join(mirror_dir, "uploads")
                shutil.copytree(uploads_dir, dest_uploads, dirs_exist_ok=True)

            # Mirror runs every 60s — quick_check (header+structure) instead
            # of full table scan keeps the per-tick cost bounded.
            verify = verify_backup_artifact(dest_db, full_check=False, source_db_path=db_path)
            if not verify["ok"]:
                raise RuntimeError(f"Mirror verification failed: {verify.get('error') or verify.get('integrity')}")

            now = datetime.datetime.now().isoformat()
            _last_mirror_sync = now
            _last_mirror_error = None
            loc_status["last_success"] = now
            loc_status["last_error"] = None
            loc_status["last_verified"] = verify["written_at"]
            loc_status["verified_sha256"] = verify["sha256"]
            if prev_state == "error":
                record_location_transition("mirror", location, "recovered", message="Mirror recovered after failures")
        except Exception as e:
            _last_mirror_error = str(e)
            loc_status["last_error"] = str(e)
            if prev_state == "ok" or prev_state == "new":
                record_location_transition("mirror", location, "failed", message=str(e))


def get_per_location_status() -> dict:
    """Per-location backup status snapshot for the admin dashboard."""
    config = load_config()
    out = {}
    for loc in config.get("backup_locations", []):
        snap = _per_location_mirror_status.get(loc, {
            "last_success": None, "last_error": None, "last_attempt": None,
        })
        # Also probe writability so the operator knows the destination is alive
        writable = False
        try:
            os.makedirs(loc, exist_ok=True)
            test = os.path.join(loc, ".write_test")
            with open(test, "w") as f:
                f.write("t")
            os.remove(test)
            writable = True
        except Exception:
            writable = False
        out[loc] = {**snap, "writable": writable}
    return out


def start_mirror_backup(interval_seconds=60):
    """Start background thread that mirrors the DB every N seconds."""
    import threading
    global _mirror_thread, _mirror_running

    if _mirror_running:
        return

    _mirror_running = True

    def _loop():
        import time
        while _mirror_running:
            try:
                run_mirror_sync()
            except Exception:
                pass
            time.sleep(interval_seconds)

    _mirror_thread = threading.Thread(target=_loop, daemon=True, name="mirror-backup")
    _mirror_thread.start()


def stop_mirror_backup():
    global _mirror_running
    _mirror_running = False


def get_mirror_status():
    return {
        "running": _mirror_running,
        "last_sync": _last_mirror_sync,
        "last_error": _last_mirror_error,
    }


# ============================================================
# Scheduled Snapshot Backup
# ============================================================

_snapshot_thread = None
_snapshot_running = False
_last_snapshot_time = None
_last_snapshot_error = None

SNAPSHOT_FOLDER = "kthealth_erp_snapshots"


def run_snapshot():
    """Take a timestamped snapshot of the DB + uploads to all backup locations,
    verify the written DB, then cleanup old snapshots.

    Snapshots are folders (not loose files) so they can carry uploads alongside
    the DB. Layout: `<location>/kthealth_erp_snapshots/snapshot_YYYYMMDD_HHMMSS/
    {kthealth_erp.db, kthealth_erp.db.verified.json, uploads/}`.
    """
    import sqlite3
    import shutil
    from app.utils.paths import get_uploads_dir
    from app.utils.backup_verify import verify_backup_artifact
    global _last_snapshot_time, _last_snapshot_error

    db_path = get_configured_db_path()
    uploads_dir = get_uploads_dir()
    config = load_config()
    backup_locations = config.get("backup_locations", [])
    retention_days = _resolve_snapshot_retention_days(config)

    if not os.path.isfile(db_path) or not backup_locations:
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_name = f"snapshot_{timestamp}"

    for location in backup_locations:
        try:
            snap_root = os.path.join(location, SNAPSHOT_FOLDER)
            snap_dir = os.path.join(snap_root, snap_name)
            os.makedirs(snap_dir, exist_ok=True)

            dest_db = os.path.join(snap_dir, "kthealth_erp.db")
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            if os.path.isdir(uploads_dir):
                shutil.copytree(uploads_dir, os.path.join(snap_dir, "uploads"), dirs_exist_ok=True)

            verify = verify_backup_artifact(dest_db, full_check=True, source_db_path=db_path)
            if not verify["ok"]:
                # Snapshot is broken — wipe it so it can't be picked as a
                # restore point and the next tick has a clean slate.
                shutil.rmtree(snap_dir, ignore_errors=True)
                raise RuntimeError(f"Snapshot verification failed: {verify.get('error') or verify.get('integrity')}")

            _cleanup_snapshots(snap_root, retention_days)

            _last_snapshot_time = datetime.datetime.now().isoformat()
            _last_snapshot_error = None
        except Exception as e:
            _last_snapshot_error = str(e)


def _resolve_snapshot_retention_days(config: dict) -> int:
    """Translate the configured retention into days. Backward-compat: older
    installs may still have `snapshot_retention_hours` set."""
    days = config.get("snapshot_retention_days")
    if days is not None:
        try:
            return max(1, int(days))
        except (TypeError, ValueError):
            pass
    legacy_hours = config.get("snapshot_retention_hours")
    if legacy_hours is not None:
        try:
            return max(1, int(legacy_hours) // 24 or 1)
        except (TypeError, ValueError):
            pass
    return 7


def _cleanup_snapshots(snap_root, retention_days):
    """Delete snapshot folders (and legacy loose files) older than retention_days."""
    import shutil
    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    if not os.path.isdir(snap_root):
        return
    for fname in os.listdir(snap_root):
        fpath = os.path.join(snap_root, fname)
        # Only touch entries we own
        if not fname.startswith("snapshot_"):
            continue
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                if os.path.isdir(fpath):
                    shutil.rmtree(fpath, ignore_errors=True)
                elif os.path.isfile(fpath):
                    os.remove(fpath)
        except Exception:
            pass


def get_snapshot_info(backup_locations):
    """Get snapshot stats across all backup locations.

    Handles both the new folder-based snapshots and legacy loose-file
    snapshots so older installs keep showing the right counts post-upgrade.
    """
    from app.utils.backup_verify import read_sidecar

    total_count = 0
    total_size_mb = 0.0
    snapshots = []

    def _push(filename, location, db_path, has_uploads, created):
        nonlocal total_count, total_size_mb
        size = os.path.getsize(db_path)
        total_count += 1
        total_size_mb += size / (1024 * 1024)
        if len(snapshots) < 10:
            sidecar = read_sidecar(db_path) or {}
            snapshots.append({
                "filename": filename,
                "location": location,
                "size_mb": round(size / (1024 * 1024), 2),
                "created": created,
                "has_uploads": has_uploads,
                "verified": bool(sidecar.get("ok")),
                "integrity": sidecar.get("integrity"),
            })

    for location in backup_locations:
        snap_root = os.path.join(location, SNAPSHOT_FOLDER)
        if not os.path.isdir(snap_root):
            continue
        for entry in sorted(os.listdir(snap_root), reverse=True):
            entry_path = os.path.join(snap_root, entry)
            # Folder layout (new)
            if os.path.isdir(entry_path) and entry.startswith("snapshot_"):
                db_path = os.path.join(entry_path, "kthealth_erp.db")
                if not os.path.isfile(db_path):
                    continue
                _push(
                    entry, location, db_path,
                    os.path.isdir(os.path.join(entry_path, "uploads")),
                    datetime.datetime.fromtimestamp(os.path.getmtime(db_path)).isoformat(),
                )
            # Loose file (legacy)
            elif entry.startswith("snapshot_") and entry.endswith(".db") and os.path.isfile(entry_path):
                _push(
                    entry, location, entry_path,
                    False,
                    datetime.datetime.fromtimestamp(os.path.getmtime(entry_path)).isoformat(),
                )

    return {
        "total_count": total_count,
        "total_size_mb": round(total_size_mb, 2),
        "recent": snapshots,
    }


def start_snapshot_backup(interval_minutes=30):
    """Start background thread that takes DB snapshots every N minutes."""
    import threading
    global _snapshot_thread, _snapshot_running

    if _snapshot_running:
        return

    _snapshot_running = True

    def _loop():
        import time
        while _snapshot_running:
            try:
                run_snapshot()
            except Exception:
                pass
            time.sleep(interval_minutes * 60)

    _snapshot_thread = threading.Thread(target=_loop, daemon=True, name="snapshot-backup")
    _snapshot_thread.start()


def stop_snapshot_backup():
    global _snapshot_running
    _snapshot_running = False


def get_snapshot_status():
    config = load_config()
    retention_days = _resolve_snapshot_retention_days(config)
    return {
        "running": _snapshot_running,
        "last_snapshot": _last_snapshot_time,
        "last_error": _last_snapshot_error,
        "interval_minutes": config.get("snapshot_interval_minutes", 30),
        "retention_days": retention_days,
        # Legacy field — kept so older frontends don't break.
        "retention_hours": retention_days * 24,
    }


# ============================================================
# Google Drive Backup
# ============================================================

_gdrive_thread = None
_gdrive_running = False
_gdrive_last_sent = None
_gdrive_last_error = None


def run_gdrive_backup():
    """Compress DB and upload to Google Drive if not already sent today."""
    import gzip
    import sqlite3
    global _gdrive_last_sent, _gdrive_last_error

    config = load_config()
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Already sent today?
    if config.get("gdrive_last_sent") == today:
        return

    # Get gdrive config from license
    try:
        from config.database import SessionLocal
        from app.models.license import License
        db = SessionLocal()
        license_record = db.query(License).order_by(License.id.desc()).first()
        db.close()
        if not license_record or not license_record.gdrive_config:
            return
        gdrive = license_record.gdrive_config
        if not gdrive.get("enabled"):
            return
    except Exception:
        return

    if not gdrive.get("folder_id"):
        return

    # Get hospital_id from license
    hospital_id = license_record.hospital_id or "UNKNOWN"

    # Compress DB
    db_path = get_configured_db_path()
    if not os.path.isfile(db_path):
        return

    try:
        # Use SQLite backup API to get a consistent copy, then gzip it
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name

        source_conn = sqlite3.connect(db_path)
        dest_conn = sqlite3.connect(tmp_path)
        source_conn.backup(dest_conn)
        dest_conn.close()
        source_conn.close()

        # Verify the temp copy before uploading — never ship a corrupt backup
        # to off-site storage.
        from app.utils.backup_verify import verify_backup_artifact
        verify = verify_backup_artifact(tmp_path, full_check=True, source_db_path=db_path)
        if not verify["ok"]:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            err = verify.get("error") or verify.get("integrity") or "unknown"
            _gdrive_last_error = f"Pre-upload verification failed: {err}"
            config["gdrive_last_error"] = _gdrive_last_error
            save_config(config)
            return

        with open(tmp_path, "rb") as f:
            compressed = gzip.compress(f.read())
        os.remove(tmp_path)
        try:
            os.remove(tmp_path + ".verified.json")
        except Exception:
            pass

        # Upload using the full gdrive config (supports both service account and OAuth)
        from app.utils.gdrive import upload_backup, cleanup_old_backups
        filename = f"backup_{today}.db.gz"
        upload_backup(gdrive, hospital_id, compressed, filename)

        # Cleanup old backups (30 day retention)
        try:
            cleanup_old_backups(gdrive, hospital_id, retention_days=30)
        except Exception:
            pass

        # Mark as sent
        config["gdrive_last_sent"] = today
        config["gdrive_last_error"] = None
        save_config(config)
        _gdrive_last_sent = today
        _gdrive_last_error = None

    except Exception as e:
        _gdrive_last_error = str(e)
        config["gdrive_last_error"] = str(e)
        save_config(config)


def start_gdrive_backup(interval_minutes=10):
    """Start background thread that checks and uploads to Google Drive."""
    import threading
    global _gdrive_thread, _gdrive_running

    if _gdrive_running:
        return

    _gdrive_running = True

    def _loop():
        import time
        while _gdrive_running:
            try:
                run_gdrive_backup()
            except Exception:
                pass
            time.sleep(interval_minutes * 60)

    _gdrive_thread = threading.Thread(target=_loop, daemon=True, name="gdrive-backup")
    _gdrive_thread.start()


def stop_gdrive_backup():
    global _gdrive_running
    _gdrive_running = False


def get_gdrive_status():
    config = load_config()
    # Check if license has gdrive enabled
    gdrive_enabled = False
    try:
        from config.database import SessionLocal
        from app.models.license import License
        db = SessionLocal()
        lic = db.query(License).order_by(License.id.desc()).first()
        db.close()
        if lic and lic.gdrive_config and lic.gdrive_config.get("enabled"):
            gdrive_enabled = True
    except Exception:
        pass

    return {
        "enabled": gdrive_enabled,
        "running": _gdrive_running,
        "last_sent": config.get("gdrive_last_sent"),
        "last_error": config.get("gdrive_last_error"),
    }
