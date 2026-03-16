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


def get_data_dir():
    """
    Get the persistent data directory.
    - Bundled: data/ next to the .exe
    - Dev: backend/ directory itself
    """
    if is_bundled():
        data_dir = os.path.join(get_base_dir(), "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    return get_base_dir()


def get_uploads_dir():
    """
    Get the uploads directory.
    - Bundled: data/uploads/ next to the .exe
    - Dev: backend/uploads/
    """
    if is_bundled():
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
    Checks config.json first for a user-chosen path (set during setup wizard).
    Falls back to:
    - Bundled: data/kthealth_erp.db next to the .exe
    - Dev: backend/kthealth_erp.db
    """
    # Check if user configured a custom DB path via setup wizard
    config_path = os.path.join(get_base_dir(), "config.json")
    if os.path.isfile(config_path):
        try:
            import json
            with open(config_path, "r") as f:
                config = json.load(f)
            custom_path = config.get("db_path", "")
            if custom_path and os.path.isdir(os.path.dirname(custom_path)):
                return custom_path
        except Exception:
            pass
    return os.path.join(get_data_dir(), "kthealth_erp.db")
