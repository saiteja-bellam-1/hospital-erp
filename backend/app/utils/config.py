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

    Truth chain:
      1. config.json explicitly says setup_complete=True, AND
      2. the DB at the configured path actually contains a usable users table
         with at least one row (sentinel-table probe).

    Falling back to "DB file exists and >0 bytes" was unsafe: a half-written
    or empty DB file would pass and the app would boot into a broken state.
    For backward compat with pre-wizard installs (where config.json didn't
    exist yet), the same sentinel probe at the default DB path also counts.
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
    from app.utils.paths import get_db_path

    if config.get("setup_complete", False):
        # Trust the flag only if the DB it points at is actually populated.
        db_path = config.get("db_path") or get_db_path()
        return _has_seeded_users(db_path)

    # Backward compat: pre-wizard installs never wrote config.json, so probe
    # the default DB path for a seeded users table.
    return _has_seeded_users(get_db_path())


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

    for location in backup_locations:
        entry = {"path": location, "success": False, "message": ""}
        try:
            # Create a timestamped backup folder
            backup_dir = os.path.join(location, backup_folder_name)
            os.makedirs(backup_dir, exist_ok=True)

            # 1. Backup database using SQLite backup API (safe while in use)
            dest_db = os.path.join(backup_dir, backup_db_name)
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            # 2. Backup uploads folder (logos, signatures, etc.)
            if os.path.isdir(uploads_dir):
                dest_uploads = os.path.join(backup_dir, "uploads")
                shutil.copytree(uploads_dir, dest_uploads, dirs_exist_ok=True)

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

    for location in backup_locations:
        loc_status = _per_location_mirror_status.setdefault(location, {
            "last_success": None, "last_error": None, "last_attempt": None,
        })
        loc_status["last_attempt"] = datetime.datetime.now().isoformat()
        try:
            mirror_dir = os.path.join(location, "kthealth_erp_mirror")
            os.makedirs(mirror_dir, exist_ok=True)

            # Mirror database
            dest_db = os.path.join(mirror_dir, mirror_db_name)
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            # Mirror uploads
            if os.path.isdir(uploads_dir):
                dest_uploads = os.path.join(mirror_dir, "uploads")
                shutil.copytree(uploads_dir, dest_uploads, dirs_exist_ok=True)

            now = datetime.datetime.now().isoformat()
            _last_mirror_sync = now
            _last_mirror_error = None
            loc_status["last_success"] = now
            loc_status["last_error"] = None
        except Exception as e:
            _last_mirror_error = str(e)
            loc_status["last_error"] = str(e)


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
    """Take a timestamped snapshot of the DB to all backup locations, then cleanup old ones."""
    import sqlite3
    global _last_snapshot_time, _last_snapshot_error

    db_path = get_configured_db_path()
    config = load_config()
    backup_locations = config.get("backup_locations", [])
    retention_hours = config.get("snapshot_retention_hours", 72)

    if not os.path.isfile(db_path) or not backup_locations:
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"snapshot_{timestamp}.db"

    for location in backup_locations:
        try:
            snap_dir = os.path.join(location, SNAPSHOT_FOLDER)
            os.makedirs(snap_dir, exist_ok=True)

            dest_db = os.path.join(snap_dir, filename)
            source_conn = sqlite3.connect(db_path)
            dest_conn = sqlite3.connect(dest_db)
            source_conn.backup(dest_conn)
            dest_conn.close()
            source_conn.close()

            # Cleanup old snapshots
            _cleanup_snapshots(snap_dir, retention_hours)

            _last_snapshot_time = datetime.datetime.now().isoformat()
            _last_snapshot_error = None
        except Exception as e:
            _last_snapshot_error = str(e)


def _cleanup_snapshots(snap_dir, retention_hours):
    """Delete snapshot files older than retention_hours."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=retention_hours)
    for fname in os.listdir(snap_dir):
        if not fname.startswith("snapshot_") or not fname.endswith(".db"):
            continue
        fpath = os.path.join(snap_dir, fname)
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
        except Exception:
            pass


def get_snapshot_info(backup_locations):
    """Get snapshot stats across all backup locations."""
    total_count = 0
    total_size_mb = 0.0
    snapshots = []

    for location in backup_locations:
        snap_dir = os.path.join(location, SNAPSHOT_FOLDER)
        if not os.path.isdir(snap_dir):
            continue
        for fname in sorted(os.listdir(snap_dir), reverse=True):
            if not fname.startswith("snapshot_") or not fname.endswith(".db"):
                continue
            fpath = os.path.join(snap_dir, fname)
            size = os.path.getsize(fpath)
            total_count += 1
            total_size_mb += size / (1024 * 1024)
            if len(snapshots) < 10:  # Return last 10
                snapshots.append({
                    "filename": fname,
                    "location": location,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "created": datetime.datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat(),
                })

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
    return {
        "running": _snapshot_running,
        "last_snapshot": _last_snapshot_time,
        "last_error": _last_snapshot_error,
        "interval_minutes": config.get("snapshot_interval_minutes", 30),
        "retention_hours": config.get("snapshot_retention_hours", 72),
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

        with open(tmp_path, "rb") as f:
            compressed = gzip.compress(f.read())
        os.remove(tmp_path)

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
