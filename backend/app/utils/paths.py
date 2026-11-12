"""
Centralized path resolution for both dev and PyInstaller bundled mode.
"""
import sys
import os


def is_bundled():
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, 'frozen', False)


def get_base_dir():
    """
    Get the base directory for the application.
    - Bundled: directory containing the .exe
    - Dev: the backend/ directory (parent of this file's package)
    """
    if is_bundled():
        return os.path.dirname(sys.executable)
    # Dev mode: backend/ directory
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_bundle_dir():
    """
    Get the directory where bundled resources are extracted.
    - Bundled: sys._MEIPASS (temp extraction folder)
    - Dev: the backend/ directory
    """
    if is_bundled():
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_config():
    """Read config.json next to the exe (or backend/ in dev). Never raises."""
    config_path = os.path.join(get_base_dir(), "config.json")
    if not os.path.isfile(config_path):
        return {}
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_configured_data_dir():
    """Return config.json ``data_dir`` when that directory exists, else ''."""
    custom = str(_read_config().get("data_dir") or "").strip()
    if custom and os.path.isdir(custom):
        return os.path.normpath(custom)
    return ""


def get_data_dir():
    """
    Get the persistent data directory.

    After "Move Data Folder", this is the folder recorded in config.json.
    Otherwise:
    - Bundled: data/ next to the .exe
    - Dev: backend/ directory itself
    """
    custom = get_configured_data_dir()
    if custom:
        os.makedirs(custom, exist_ok=True)
        return custom
    if is_bundled():
        data_dir = os.path.join(get_base_dir(), "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    return get_base_dir()


def get_state_dir():
    """Directory for logs, version.txt, and the other install state files.

    Follows a moved data folder. Before a move, bundled installs use
    ``<exe>/data`` and dev uses ``<backend>/data`` (logs never lived in the
    source tree root).
    """
    if get_configured_data_dir() or is_bundled():
        return get_data_dir()
    path = os.path.join(get_base_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def get_uploads_dir():
    """
    Get the uploads directory.

    Follows a moved data folder. Otherwise:
    - Bundled: data/uploads/ next to the .exe
    - Dev: backend/uploads/
    """
    if is_bundled() or get_configured_data_dir():
        uploads_dir = os.path.join(get_data_dir(), "uploads")
    else:
        uploads_dir = os.path.join(get_base_dir(), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    return uploads_dir


def get_frontend_dir():
    """
    Get the frontend build directory.
    - Bundled: frontend_build/ inside the extracted bundle
    - Dev: frontend/build/ relative to project root
    """
    if is_bundled():
        return os.path.join(get_bundle_dir(), "frontend_build")
    # Dev mode: check for frontend/build relative to project root
    project_root = os.path.dirname(get_base_dir())
    return os.path.join(project_root, "frontend", "build")


def get_db_path():
    """
    Get the SQLite database file path.

    A moved data folder wins: the database is ``<data_dir>/kthealth_erp.db``.
    Otherwise config.json ``db_path`` is used when its parent directory exists
    (the older database-only move). Falls back to:
    - Bundled: data/kthealth_erp.db next to the .exe
    - Dev: backend/kthealth_erp.db
    """
    if get_configured_data_dir():
        return os.path.join(get_data_dir(), "kthealth_erp.db")
    custom_path = str(_read_config().get("db_path") or "").strip()
    if custom_path and os.path.isdir(os.path.dirname(custom_path)):
        return custom_path
    return os.path.join(get_data_dir(), "kthealth_erp.db")
