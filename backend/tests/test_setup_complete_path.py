"""is_setup_complete must probe the same DB path the engine uses."""
import json
import sqlite3


def _write_users_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("INSERT INTO users (username) VALUES ('admin')")
    conn.commit()
    conn.close()


def test_setup_complete_ignores_unreachable_custom_db_path(tmp_path, monkeypatch):
    """Stale absolute paths from another OS must not flip setup incomplete."""
    from app.utils import config as cfg
    from app.utils import paths

    live_db = tmp_path / "kthealth_erp.db"
    _write_users_db(str(live_db))

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "setup_complete": True,
        # Unreachable on this machine (Windows-style absolute path).
        "db_path": r"C:\Users\other\Projects\hospital-erp\backend\kthealth_erp.db",
    }))

    monkeypatch.setattr(cfg, "_get_config_path", lambda: str(config_file))
    monkeypatch.setattr(paths, "get_db_path", lambda: str(live_db))

    assert cfg.is_setup_complete() is True


def test_setup_complete_false_when_flag_missing(tmp_path, monkeypatch):
    from app.utils import config as cfg
    from app.utils import paths

    live_db = tmp_path / "kthealth_erp.db"
    _write_users_db(str(live_db))

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"setup_complete": False}))

    monkeypatch.setattr(cfg, "_get_config_path", lambda: str(config_file))
    monkeypatch.setattr(paths, "get_db_path", lambda: str(live_db))

    assert cfg.is_setup_complete() is False
