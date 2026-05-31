"""Apply an installer-collected seed file on first launch.

The Inno Setup wizard is the ONLY install path. It collects hospital info,
admin credentials, license, backup paths, optional pre-existing data folder,
and writes:

  <data-dir>/install_seed.json
  <data-dir>/.install_seed.pwd      (password only, ACL-locked)

On first launch the launcher calls :func:`consume_seed_if_present`. We:

  * read both files,
  * run the DB seeding path (`app.services.db_seed.init_database_and_seed`),
  * apply the license if one was selected,
  * persist backup destinations to ``config.json``,
  * delete the seed files on success (so a re-launch is a no-op).

If anything fails we log the traceback to ``data/.bootstrap_status.json`` and
**leave the seed files in place** so the operator can fix the problem (e.g.
remove a bad ``.lic`` reference) and re-launch.

If no seed file is present and `setup_complete` is false in ``config.json``,
the app boots into a state with no admin user; the operator must run the
installer (Windows) or supply an `install_seed.json` manually (dev/source).
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import traceback
from typing import Optional

log = logging.getLogger("bootstrap_from_seed")

SEED_FILENAME = "install_seed.json"
PWD_FILENAME = ".install_seed.pwd"
STATUS_FILENAME = ".bootstrap_status.json"

MIN_PASSWORD_LEN = 8


def _data_dir(exe_dir: str) -> str:
    return os.path.join(exe_dir, "data")


def _paths(exe_dir: str):
    d = _data_dir(exe_dir)
    return (
        os.path.join(d, SEED_FILENAME),
        os.path.join(d, PWD_FILENAME),
        os.path.join(d, STATUS_FILENAME),
    )


def _read_pwd_file(pwd_path: str) -> str:
    """Read the installer-supplied password file.

    The Inno Setup wizard used to icacls the file down to SYSTEM +
    Administrators after writing it (for "defence in depth" on the plaintext
    password). But the [Run] block then relaunches the .exe as the invoking
    USER token (not elevated), so the very process that needs to consume
    this file gets PermissionError. The lockdown has since been dropped in
    new installers, but already-broken installs still have the bad ACL on
    disk. To make those self-recover, on PermissionError we try once to
    reset inheritance via icacls and re-read.
    """
    try:
        with open(pwd_path) as f:
            return f.read().rstrip("\r\n")
    except PermissionError as e:
        log.warning("PermissionError reading %s — attempting icacls self-heal", pwd_path)
        if not _try_unlock_pwd_file(pwd_path):
            raise PermissionError(
                f"Cannot read {pwd_path}: {e}. The installer locked this file to "
                f"Administrators only and the launcher is not running elevated. "
                f"Run icacls \"{pwd_path}\" /reset, or right-click KTHEALTHERP.exe "
                f"and 'Run as administrator' once to complete first-launch setup."
            )
        with open(pwd_path) as f:
            return f.read().rstrip("\r\n")


def _try_unlock_pwd_file(pwd_path: str) -> bool:
    """Best-effort icacls /reset so an already-locked .pwd file becomes
    readable by the current process. Returns True only if a subsequent
    open() can read the file.
    """
    import subprocess
    try:
        subprocess.run(
            ["icacls", pwd_path, "/reset"],
            capture_output=True, timeout=10, check=False,
        )
    except Exception:
        return False
    try:
        with open(pwd_path) as f:
            f.read(1)
        return True
    except Exception:
        return False


def _write_status(status_path: str, payload: dict) -> None:
    try:
        os.makedirs(os.path.dirname(status_path), exist_ok=True)
        with open(status_path, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        log.warning("Could not write bootstrap status to %s", status_path, exc_info=True)


def consume_seed_if_present(exe_dir: str) -> Optional[dict]:
    """If a seed file is present, apply it and return a status dict.

    Returns ``None`` when no seed exists (normal steady-state). Returns a dict
    with ``applied: True`` on success and ``applied: False`` on failure.
    """
    seed_path, pwd_path, status_path = _paths(exe_dir)
    if not os.path.isfile(seed_path):
        return None

    log.info("Installer seed detected at %s; applying...", seed_path)
    try:
        with open(seed_path) as f:
            seed = json.load(f)

        password = ""
        if os.path.isfile(pwd_path):
            password = _read_pwd_file(pwd_path)

        mode = seed.get("mode", "fresh")
        if mode == "fresh":
            _apply_fresh(seed, password)
        elif mode == "adopt_existing":
            _apply_adopt(seed)
        elif mode == "restore_backup":
            _apply_restore(seed)
        else:
            raise ValueError(f"Unknown seed mode: {mode!r}")

        for p in (seed_path, pwd_path):
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:
                log.warning("Could not remove %s after apply", p, exc_info=True)

        status = {
            "applied": True,
            "mode": mode,
            "at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        users_result = seed.get("_users_import_result")
        if users_result is not None:
            status["users_import"] = users_result
        _write_status(status_path, status)
        log.info("Installer seed applied (mode=%s)", mode)
        return status
    except Exception as e:
        tb = traceback.format_exc()
        log.error("Installer seed apply failed: %s\n%s", e, tb)
        status = {
            "applied": False,
            "error": str(e),
            "traceback": tb,
            "at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        _write_status(status_path, status)
        return status


def _validate_backup_locations(seed_locations) -> list:
    out = []
    for loc in seed_locations or []:
        loc = (loc or "").strip()
        if not loc:
            continue
        try:
            os.makedirs(loc, exist_ok=True)
            out.append(loc)
        except Exception:
            log.warning("Skipping unwritable backup location %r", loc)
    return out


def _apply_fresh(seed: dict, password: str) -> None:
    """Fresh install: create DB at the chosen folder, seed roles + admin, apply license."""
    if not seed.get("admin_username"):
        raise ValueError("seed missing admin_username")
    if not seed.get("hospital_name"):
        raise ValueError("seed missing hospital_name")
    if not password:
        raise ValueError("password file missing or empty")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password too short (min {MIN_PASSWORD_LEN} chars)")

    from app.services.db_seed import init_database_and_seed, store_license
    from app.utils.config import save_config
    from app.utils.paths import get_data_dir

    data_dir = (seed.get("data_dir") or "").strip() or get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "kthealth_erp.db")

    backup_locations = _validate_backup_locations(seed.get("backup_locations"))

    config = {
        "setup_complete": True,
        "db_path": db_path,
        "backup_locations": backup_locations,
        "hospital_name": seed.get("hospital_name", ""),
    }
    save_config(config)

    seed_dict = {
        "hospital_name": seed.get("hospital_name", ""),
        "hospital_address": seed.get("hospital_address", "") or "",
        "hospital_phone": seed.get("hospital_phone", "") or "",
        "hospital_email": seed.get("hospital_email", "") or "",
        "mrn_prefix": (seed.get("mrn_prefix") or "KTH"),
        "admin_username": seed["admin_username"],
        "admin_email": seed.get("admin_email") or f"{seed['admin_username']}@local",
        "admin_password": password,
        "admin_first_name": seed.get("admin_first_name") or "System",
        "admin_last_name": seed.get("admin_last_name") or "Administrator",
    }

    try:
        init_database_and_seed(seed_dict, db_path)
    except Exception:
        # Roll the setup_complete flag back so a retry isn't blocked.
        config["setup_complete"] = False
        save_config(config)
        # Best-effort cleanup of any half-written DB.
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                p = db_path + suffix
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass
        raise

    from config.database import reinitialize_engine
    reinitialize_engine()

    license_path = (seed.get("license_path") or "").strip()
    if license_path:
        if not os.path.isfile(license_path):
            log.warning("License path %s not found; skipping license install", license_path)
        else:
            try:
                with open(license_path, "r", encoding="utf-8") as f:
                    content = f.read()
                result = store_license(content, db_path)
                if not result.get("stored"):
                    log.warning("License install failed: %s", result.get("error"))
            except Exception as e:
                log.warning("License install raised %s — operator can upload from Dashboard", e)

    # Bulk user import (optional).
    users_csv_path = (seed.get("users_csv_path") or "").strip()
    if users_csv_path:
        seed["_users_import_result"] = _apply_users_csv(users_csv_path, db_path)


def _apply_users_csv(csv_path: str, db_path: str) -> dict:
    """Parse + apply an installer-supplied users CSV.

    Failures here are non-fatal for bootstrap: super_admin already exists and
    the operator can re-import from the in-app screen later. Returns a status
    dict that the caller stitches into ``.bootstrap_status.json``.
    """
    if not os.path.isfile(csv_path):
        log.warning("users_csv_path %s not found; skipping bulk user import", csv_path)
        return {"applied": False, "reason": "file_not_found", "path": csv_path}

    try:
        from app.services.user_csv_import import (
            INSTALLER_ALLOWED_ROLES,
            apply_users,
            parse_and_validate_file,
        )
        from app.models.hospital import Hospital
        from app.models.user import User
        from config.database import SessionLocal

        db = SessionLocal()
        try:
            existing_usernames = [u for (u,) in db.query(User.username).all()]
            existing_emails = [e for (e,) in db.query(User.email).all()]
            rows, errors = parse_and_validate_file(
                csv_path,
                allowed_roles=INSTALLER_ALLOWED_ROLES,
                existing_usernames=existing_usernames,
                existing_emails=existing_emails,
            )
            if errors:
                log.warning(
                    "Bulk user import rejected — %d row(s) had errors. Leaving "
                    "%s in place for operator to fix and retry.",
                    len(errors), csv_path,
                )
                return {
                    "applied": False,
                    "reason": "validation_failed",
                    "errors": [e.as_dict() for e in errors],
                    "path": csv_path,
                }

            hospital = db.query(Hospital).first()
            if hospital is None:
                return {"applied": False, "reason": "no_hospital_row", "path": csv_path}

            result = apply_users(db, rows, hospital.id)
        finally:
            db.close()

        try:
            os.remove(csv_path)
        except Exception:
            log.warning("Could not remove %s after import", csv_path, exc_info=True)

        log.info("Bulk user import created %d user(s)", result["created"])
        return {
            "applied": True,
            "created": result["created"],
            "usernames": result["usernames"],
        }
    except Exception as e:
        log.error("Bulk user import raised %s; leaving CSV in place", e, exc_info=True)
        return {
            "applied": False,
            "reason": "exception",
            "error": str(e),
            "path": csv_path,
        }


def _apply_restore(seed: dict) -> None:
    """Operator picked a single .db backup file at install time. We copy it
    into the target data folder using the SQLite backup API, then rebind
    config.json + the engine to it. Migrations run so the restored DB picks
    up any newer columns introduced by this build.
    """
    import sqlite3
    from app.utils.config import save_config

    data_dir = (seed.get("data_dir") or "").strip()
    backup_file = (seed.get("backup_file_path") or "").strip()
    if not data_dir:
        raise ValueError("restore_backup seed missing data_dir")
    if not backup_file:
        raise ValueError("restore_backup seed missing backup_file_path")
    if not os.path.isfile(backup_file):
        raise ValueError(f"backup file not found: {backup_file}")

    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "kthealth_erp.db")
    if os.path.isfile(db_path) and os.path.getsize(db_path) > 0:
        raise ValueError(f"target DB already exists at {db_path} — refusing to overwrite during install")

    backup_locations = _validate_backup_locations(seed.get("backup_locations"))

    # Copy via SQLite backup API (safe even if the source is a hot copy).
    src = sqlite3.connect(f"file:{backup_file}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(db_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    config = {
        "setup_complete": True,
        "db_path": db_path,
        "backup_locations": backup_locations,
    }
    save_config(config)

    from config.database import reinitialize_engine
    reinitialize_engine()

    # Bring schema forward in case the restored DB came from an older build.
    try:
        from migrate_patient_fields import migrate
        migrate()
    except Exception:
        log.warning("Post-restore migrate() failed; non-fatal", exc_info=True)


def _apply_adopt(seed: dict) -> None:
    """Operator pointed the installer at an existing data folder. Don't seed —
    just rebind config.json + the engine to the existing DB.
    """
    from app.utils.config import load_config, save_config

    data_dir = (seed.get("data_dir") or "").strip()
    if not data_dir:
        raise ValueError("adopt_existing seed missing data_dir")
    if not os.path.isdir(data_dir):
        raise ValueError(f"data folder not found: {data_dir}")
    db_path = os.path.join(data_dir, "kthealth_erp.db")
    if not os.path.isfile(db_path):
        raise ValueError(f"existing DB not found at {db_path}")

    backup_locations = _validate_backup_locations(seed.get("backup_locations"))

    config = load_config()
    config["setup_complete"] = True
    config["db_path"] = db_path
    if backup_locations:
        config["backup_locations"] = backup_locations
    save_config(config)

    from config.database import reinitialize_engine
    reinitialize_engine()
