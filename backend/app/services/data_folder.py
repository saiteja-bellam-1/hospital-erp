"""Move the hospital data folder, and measure what is stored in it.

The database, uploads, logs, and the small state files (version, machine id,
hidden markers) move together. ``config.json`` stays next to the executable
and is rewritten so the next read of ``get_data_dir()`` follows the new folder.

Installer seed files are left where the launcher looks for them
(``<exe>\\data``). A dev checkout is not a data folder: only the hospital
files are moved, never the source tree.
"""
from __future__ import annotations

import os
import shutil
import sqlite3

DB_FILENAME = "kthealth_erp.db"
_DB_SIDECARS = ("-journal", "-wal", "-shm")
# The launcher reads these from <exe>\data on first boot. Moving them would
# strand a retry that has not consumed the seed yet.
_LEAVE_BEHIND = {"install_seed.json", ".install_seed.pwd", "install_users.csv"}
_SKIP_COPY = _LEAVE_BEHIND | {DB_FILENAME, *(DB_FILENAME + suffix for suffix in _DB_SIDECARS)}


class DataFolderError(Exception):
    """A move the operator can correct (bad path, collision, failed copy)."""


def _is_source_tree(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "main.py")) and os.path.isdir(os.path.join(path, "app"))


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _is_inside(child: str, parent: str) -> bool:
    child_n = os.path.normcase(os.path.abspath(child))
    parent_n = os.path.normcase(os.path.abspath(parent))
    if child_n == parent_n:
        return True
    try:
        return os.path.commonpath([child_n, parent_n]) == parent_n
    except ValueError:
        return False


def _plan_items(data_root: str) -> list[tuple[str, str]]:
    """Files and folders to copy, as (source, name-inside-destination)."""
    items: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(src: str, rel: str) -> None:
        if rel in seen or rel in _SKIP_COPY or not os.path.exists(src):
            return
        seen.add(rel)
        items.append((src, rel))

    if _is_source_tree(data_root):
        add(os.path.join(data_root, "uploads"), "uploads")
        add(os.path.join(data_root, "machine_id.txt"), "machine_id.txt")
        nested = os.path.join(data_root, "data")
        if os.path.isdir(nested) and not _is_source_tree(nested):
            for name in os.listdir(nested):
                add(os.path.join(nested, name), name)
        return items

    if os.path.isdir(data_root):
        for name in os.listdir(data_root):
            add(os.path.join(data_root, name), name)
    return items


def _sqlite_backup(src: str, dest: str) -> None:
    source = sqlite3.connect(src)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _verify_db(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if not row or row[0] != "ok":
        detail = row[0] if row else "no result"
        raise DataFolderError(f"Moved database failed its integrity check: {detail}")


def _remove_tree(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _rollback(created: list[str]) -> None:
    for path in reversed(created):
        try:
            _remove_tree(path)
        except OSError:
            pass


def _db_files_to_remove(data_root: str, db_path: str) -> list[str]:
    bases = []
    if db_path and os.path.isfile(db_path):
        bases.append(db_path)
    inside = os.path.join(data_root, DB_FILENAME)
    if os.path.isfile(inside) and not any(_same_path(inside, base) for base in bases):
        bases.append(inside)
    out = []
    for base in bases:
        out.append(base)
        for suffix in _DB_SIDECARS:
            sidecar = base + suffix
            if os.path.isfile(sidecar):
                out.append(sidecar)
    return out


def relocate_data_folder(
    new_folder: str,
    *,
    data_root: str,
    db_path: str,
    before_delete=None,
) -> dict:
    """Copy the data folder to ``new_folder``, point config at it, then delete the source.

    ``before_delete`` runs after config.json is updated and before the old
    files are removed, so the caller can drop SQLite locks first.
    """
    from app.utils.config import load_config, save_config

    dest = os.path.normpath(os.path.abspath(os.path.expanduser(str(new_folder or "").strip().strip('"'))))
    data_root = os.path.normpath(os.path.abspath(data_root))
    db_path = os.path.abspath(db_path) if db_path else ""

    if not dest:
        raise DataFolderError("New folder path is required")
    if _same_path(dest, data_root):
        raise DataFolderError("New location is the same as the current data folder")
    if _is_inside(dest, data_root) and not _same_path(dest, data_root):
        raise DataFolderError("The new folder is inside the current data folder. Choose a folder outside it.")
    if not os.path.isfile(db_path):
        raise DataFolderError("Current database file not found")

    try:
        os.makedirs(dest, exist_ok=True)
        probe = os.path.join(dest, ".write_test")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("test")
        os.remove(probe)
    except PermissionError:
        raise DataFolderError("Permission denied. Cannot write to this location.")
    except OSError as exc:
        raise DataFolderError(f"Invalid path: {exc}")

    dest_db = os.path.join(dest, DB_FILENAME)
    if _same_path(dest_db, db_path):
        raise DataFolderError("New location is the same as the current data folder")
    if os.path.exists(dest_db):
        raise DataFolderError("That folder already contains kthealth_erp.db. Choose an empty folder.")

    items = _plan_items(data_root)
    for _src, rel in items:
        if os.path.exists(os.path.join(dest, rel)):
            raise DataFolderError(f"That folder already contains {rel}. Choose an empty folder.")

    created: list[str] = []
    try:
        _sqlite_backup(db_path, dest_db)
        created.append(dest_db)
        _verify_db(dest_db)
        for src, rel in items:
            target = os.path.join(dest, rel)
            if os.path.isdir(src) and not os.path.islink(src):
                shutil.copytree(src, target, symlinks=True)
            else:
                shutil.copy2(src, target, follow_symlinks=False)
            created.append(target)
    except DataFolderError:
        _rollback(created)
        raise
    except Exception as exc:
        _rollback(created)
        raise DataFolderError(f"Could not move the data folder: {exc}") from exc

    try:
        config = load_config()
        config["data_dir"] = dest
        config["db_path"] = dest_db
        save_config(config)
    except Exception as exc:
        _rollback(created)
        raise DataFolderError(f"Could not update config.json: {exc}") from exc

    if before_delete:
        try:
            before_delete()
        except Exception:
            pass

    leftovers: list[str] = []
    for path in _db_files_to_remove(data_root, db_path):
        if _is_inside(path, dest):
            continue
        try:
            _remove_tree(path)
        except OSError:
            leftovers.append(path)
    for src, _rel in items:
        if _is_inside(src, dest):
            continue
        try:
            _remove_tree(src)
        except OSError:
            leftovers.append(src)

    if not _is_source_tree(data_root):
        try:
            os.rmdir(data_root)
        except OSError:
            pass
    else:
        nested = os.path.join(data_root, "data")
        try:
            os.rmdir(nested)
        except OSError:
            pass

    message = "Data folder moved."
    if leftovers:
        message += " Some files are still open in the old folder and stay there until the app restarts."

    return {
        "message": message,
        "old_path": data_root,
        "new_path": dest,
        "db_path": dest_db,
        "moved": [DB_FILENAME, *[rel for _src, rel in items]],
        "leftovers": leftovers,
        "restart_recommended": bool(leftovers),
    }


def _measure(path: str) -> tuple[int, int]:
    """Return (bytes, file_count). Symlinks are counted as themselves."""
    if os.path.islink(path) or os.path.isfile(path):
        try:
            return os.path.getsize(path), 1
        except OSError:
            return 0, 1
    total = 0
    files = 0
    for root, _dirs, filenames in os.walk(path, followlinks=False):
        for name in filenames:
            files += 1
            fp = os.path.join(root, name)
            if os.path.islink(fp):
                continue
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total, files


def _entry(path: str, name: str, *, with_children: bool) -> dict:
    size, count = _measure(path)
    is_dir = os.path.isdir(path) and not os.path.islink(path)
    children = []
    if with_children and is_dir:
        try:
            names = os.listdir(path)
        except OSError:
            names = []
        for child in names:
            children.append(_entry(os.path.join(path, child), child, with_children=False))
        children.sort(key=lambda item: item["bytes"], reverse=True)
        if len(children) > 500:
            children = children[:500]
    return {
        "name": name,
        "path": path,
        "is_dir": is_dir,
        "bytes": size,
        "file_count": count,
        "hidden": name.startswith("."),
        "children": children,
    }


def _scan_directory(root: str) -> list[dict]:
    if not os.path.isdir(root):
        return []
    entries = []
    try:
        names = os.listdir(root)
    except OSError:
        return []
    for name in names:
        entries.append(_entry(os.path.join(root, name), name, with_children=True))
    entries.sort(key=lambda item: item["bytes"], reverse=True)
    return entries


def describe_storage(data_root: str | None = None, db_path: str | None = None) -> dict:
    """Size of the data folder, including hidden files.

    A dev checkout is not walked in full. Only the hospital files (database,
    uploads, machine id, and the ``data`` state folder) are measured.
    """
    if data_root is None or db_path is None:
        from app.utils.config import get_configured_db_path
        from app.utils.paths import get_data_dir
        if data_root is None:
            data_root = get_data_dir()
        if db_path is None:
            db_path = get_configured_db_path()

    data_root = os.path.abspath(data_root)
    source_tree = _is_source_tree(data_root)
    if source_tree:
        entries = []
        for src, rel in _plan_items(data_root):
            entries.append(_entry(src, rel, with_children=True))
        if db_path and os.path.isfile(db_path):
            entries.append(_entry(db_path, os.path.basename(db_path), with_children=False))
            for suffix in _DB_SIDECARS:
                sidecar = db_path + suffix
                if os.path.isfile(sidecar):
                    entries.append(_entry(sidecar, os.path.basename(sidecar), with_children=False))
        entries.sort(key=lambda item: item["bytes"], reverse=True)
    else:
        entries = _scan_directory(data_root)
        outside = db_path and os.path.isfile(db_path) and not _is_inside(db_path, data_root)
        if outside:
            entries.append(_entry(db_path, os.path.basename(db_path), with_children=False))
            entries.sort(key=lambda item: item["bytes"], reverse=True)

    total_bytes = sum(item["bytes"] for item in entries)
    total_files = sum(item["file_count"] for item in entries)
    return {
        "data_dir": data_root,
        "source_tree": source_tree,
        "total_bytes": total_bytes,
        "total_files": total_files,
        "entries": entries,
        "note": (
            "Development checkout. These are the hospital files, not the source tree."
            if source_tree else ""
        ),
    }
