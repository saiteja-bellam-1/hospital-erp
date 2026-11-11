"""Move the whole data folder, and report what storage it uses."""
import json
import os
import sqlite3

import pytest


def _make_db(path, username="admin"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
    conn.commit()
    conn.close()


def _username(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT username FROM users").fetchone()[0]
    finally:
        conn.close()


def _patch_config(monkeypatch, initial=None):
    box = dict(initial or {})

    def load():
        return dict(box)

    def save(cfg):
        box.clear()
        box.update(cfg)

    monkeypatch.setattr("app.utils.config.load_config", load)
    monkeypatch.setattr("app.utils.config.save_config", save)
    return box


def test_relocate_moves_folder_including_hidden_files(tmp_path, monkeypatch):
    from app.services.data_folder import relocate_data_folder

    src = tmp_path / "data"
    (src / "uploads").mkdir(parents=True)
    (src / "uploads" / "logo.png").write_bytes(b"png")
    (src / "logs").mkdir()
    (src / "logs" / "server.log").write_text("boot", encoding="utf-8")
    (src / ".runtime_port").write_text("8000", encoding="utf-8")
    (src / ".bootstrap_status.json").write_text("{}", encoding="utf-8")
    (src / "install_seed.json").write_text("{}", encoding="utf-8")
    db = src / "kthealth_erp.db"
    _make_db(str(db))
    # A hot sidecar must not be copied as the live database.
    (src / "kthealth_erp.db-wal").write_bytes(b"wal")

    dest = tmp_path / "HospitalData"
    saved = _patch_config(monkeypatch, {"setup_complete": True, "db_path": str(db)})

    result = relocate_data_folder(str(dest), data_root=str(src), db_path=str(db))

    assert result["new_path"] == str(dest)
    assert _username(str(dest / "kthealth_erp.db")) == "admin"
    assert (dest / "uploads" / "logo.png").read_bytes() == b"png"
    assert (dest / "logs" / "server.log").read_text(encoding="utf-8") == "boot"
    assert (dest / ".runtime_port").read_text(encoding="utf-8") == "8000"
    assert (dest / ".bootstrap_status.json").read_text(encoding="utf-8") == "{}"
    assert not (dest / "kthealth_erp.db-wal").exists()
    assert not (dest / "install_seed.json").exists()
    assert (src / "install_seed.json").read_text(encoding="utf-8") == "{}"
    assert not db.exists()
    assert not (src / "uploads").exists()
    assert not (src / ".runtime_port").exists()
    assert saved["data_dir"] == str(dest)
    assert saved["db_path"] == str(dest / "kthealth_erp.db")
    assert saved["setup_complete"] is True


def test_relocate_source_tree_leaves_code_behind(tmp_path, monkeypatch):
    from app.services.data_folder import relocate_data_folder

    root = tmp_path / "backend"
    (root / "app").mkdir(parents=True)
    (root / "main.py").write_text("# app", encoding="utf-8")
    (root / "config.json").write_text("{}", encoding="utf-8")
    (root / "uploads").mkdir()
    (root / "uploads" / "logo.png").write_bytes(b"png")
    (root / "data" / "logs").mkdir(parents=True)
    (root / "data" / "logs" / "backup.log").write_text("err", encoding="utf-8")
    (root / "data" / "version.txt").write_text("1.2.0", encoding="utf-8")
    (root / "data" / "install_seed.json").write_text("{}", encoding="utf-8")
    (root / "machine_id.txt").write_text("ABCD", encoding="utf-8")
    db = root / "kthealth_erp.db"
    _make_db(str(db))

    dest = tmp_path / "HospitalData"
    saved = _patch_config(monkeypatch)

    relocate_data_folder(str(dest), data_root=str(root), db_path=str(db))

    assert (root / "main.py").is_file()
    assert (root / "app").is_dir()
    assert (root / "config.json").is_file()
    assert (root / "data" / "install_seed.json").is_file()
    assert not (root / "uploads").exists()
    assert not (root / "machine_id.txt").exists()
    assert not db.exists()
    assert not (root / "data" / "logs").exists()
    assert (dest / "uploads" / "logo.png").read_bytes() == b"png"
    assert (dest / "logs" / "backup.log").read_text(encoding="utf-8") == "err"
    assert (dest / "version.txt").read_text(encoding="utf-8") == "1.2.0"
    assert (dest / "machine_id.txt").read_text(encoding="utf-8") == "ABCD"
    assert saved["data_dir"] == str(dest)


def test_relocate_replaces_external_database(tmp_path, monkeypatch):
    from app.services.data_folder import relocate_data_folder

    root = tmp_path / "data"
    (root / "uploads").mkdir(parents=True)
    (root / "uploads" / "a.txt").write_text("a", encoding="utf-8")
    stale = root / "kthealth_erp.db"
    _make_db(str(stale), username="stale")
    external = tmp_path / "custom" / "kthealth_erp.db"
    _make_db(str(external), username="live")

    dest = tmp_path / "newhome"
    _patch_config(monkeypatch, {"db_path": str(external)})

    relocate_data_folder(str(dest), data_root=str(root), db_path=str(external))

    assert _username(str(dest / "kthealth_erp.db")) == "live"
    assert (dest / "uploads" / "a.txt").read_text(encoding="utf-8") == "a"
    assert not external.exists()
    assert not stale.exists()


def test_relocate_rejects_folder_inside_itself_and_collisions(tmp_path, monkeypatch):
    from app.services.data_folder import DataFolderError, relocate_data_folder

    root = tmp_path / "data"
    root.mkdir()
    db = root / "kthealth_erp.db"
    _make_db(str(db))
    (root / "uploads").mkdir()
    _patch_config(monkeypatch)

    with pytest.raises(DataFolderError, match="inside"):
        relocate_data_folder(str(root / "nested"), data_root=str(root), db_path=str(db))

    occupied = tmp_path / "occupied"
    (occupied / "uploads").mkdir(parents=True)
    with pytest.raises(DataFolderError, match="uploads"):
        relocate_data_folder(str(occupied), data_root=str(root), db_path=str(db))

    assert db.is_file()
    assert (root / "uploads").is_dir()


def test_storage_counts_hidden_files_and_folder_sizes(tmp_path):
    from app.services.data_folder import describe_storage

    root = tmp_path / "data"
    (root / "uploads").mkdir(parents=True)
    (root / "uploads" / "a.txt").write_bytes(b"12345")
    (root / ".runtime_port").write_text("8000", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "server.log").write_text("hello", encoding="utf-8")
    db = root / "kthealth_erp.db"
    _make_db(str(db))

    report = describe_storage(str(root), str(db))
    by_name = {entry["name"]: entry for entry in report["entries"]}

    assert ".runtime_port" in by_name
    assert by_name[".runtime_port"]["hidden"] is True
    assert by_name["uploads"]["bytes"] == 5
    assert by_name["uploads"]["children"][0]["name"] == "a.txt"
    assert by_name["logs"]["file_count"] == 1
    assert report["total_files"] == sum(entry["file_count"] for entry in report["entries"])
    assert report["total_bytes"] == sum(entry["bytes"] for entry in report["entries"])
    assert report["source_tree"] is False


def test_storage_on_a_source_tree_skips_code(tmp_path):
    from app.services.data_folder import describe_storage

    root = tmp_path / "backend"
    (root / "app").mkdir(parents=True)
    (root / "main.py").write_text("print('big')\n" * 1000, encoding="utf-8")
    (root / "uploads").mkdir()
    (root / "uploads" / "a.txt").write_bytes(b"xy")
    db = root / "kthealth_erp.db"
    _make_db(str(db))

    report = describe_storage(str(root), str(db))
    names = {entry["name"] for entry in report["entries"]}
    assert names == {"uploads", "kthealth_erp.db"}
    assert report["source_tree"] is True
    assert report["total_bytes"] < 10000


def test_paths_follow_configured_data_dir(tmp_path, monkeypatch):
    from app.utils import paths

    base = tmp_path / "install"
    base.mkdir()
    data = tmp_path / "hospital-data"
    data.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    (base / "config.json").write_text(json.dumps({
        "data_dir": str(data),
        "db_path": str(old / "kthealth_erp.db"),
    }), encoding="utf-8")
    monkeypatch.setattr(paths, "get_base_dir", lambda: str(base))
    monkeypatch.setattr(paths, "is_bundled", lambda: True)

    assert paths.get_configured_data_dir() == str(data)
    assert paths.get_data_dir() == str(data)
    assert paths.get_state_dir() == str(data)
    assert paths.get_db_path() == os.path.join(str(data), "kthealth_erp.db")
    assert paths.get_uploads_dir() == os.path.join(str(data), "uploads")

    from app.utils.config import get_configured_db_path
    assert get_configured_db_path() == os.path.join(str(data), "kthealth_erp.db")


def test_paths_keep_legacy_db_path_until_a_folder_move(tmp_path, monkeypatch):
    from app.utils import paths

    base = tmp_path / "install"
    base.mkdir()
    old = tmp_path / "old"
    old.mkdir()
    db = old / "kthealth_erp.db"
    db.write_text("", encoding="utf-8")
    (base / "config.json").write_text(json.dumps({"db_path": str(db)}), encoding="utf-8")
    monkeypatch.setattr(paths, "get_base_dir", lambda: str(base))
    monkeypatch.setattr(paths, "is_bundled", lambda: True)

    assert paths.get_configured_data_dir() == ""
    assert paths.get_db_path() == str(db)
