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
    Also returns True if a database already exists (backward compatibility
    for existing installations that pre-date the setup wizard).
    """
    config = load_config()
    if config.get("setup_complete", False):
        return True

    # Backward compat: if DB file already exists, setup was done before the wizard existed
    from app.utils.paths import get_db_path
    db_path = get_db_path()
    if os.path.isfile(db_path) and os.path.getsize(db_path) > 0:
        return True

    return False


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
