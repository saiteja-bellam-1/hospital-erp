"""Apply an installer-collected seed file on first launch.

The Inno Setup wizard collects all the inputs the operator used to type into
the React Setup Wizard (hospital info, admin credentials, license, backup
paths, optional pre-existing data folder) and writes them to:

  <data-dir>/install_seed.json
  <data-dir>/.install_seed.pwd      (password only, ACL-locked)

On first launch the launcher calls :func:`consume_seed_if_present`. We:

  * read both files,
  * run the same DB seeding path the React wizard runs (`_init_database_and_seed`),
  * apply the license if one was selected,
  * persist backup destinations to ``config.json``,
  * delete the seed files on success (so a re-launch is a no-op).

If anything fails we log the traceback to ``data/.bootstrap_status.json`` and
**leave the seed files in place** so the operator can fix the problem (e.g.
remove a bad ``.lic`` reference) and re-launch.

The React ``SetupWizard`` is kept as the fallback path: if no seed file is
present the app behaves exactly as before.
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
            with open(pwd_path) as f:
                password = f.read().rstrip("\r\n")

        mode = seed.get("mode", "fresh")
        if mode == "fresh":
            _apply_fresh(seed, password)
        elif mode == "adopt_existing":
            _apply_adopt(seed)
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

    from app.routes.setup import SetupRequest, _init_database_and_seed, _store_license
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

    req = SetupRequest(
        hospital_name=seed.get("hospital_name", ""),
        hospital_address=seed.get("hospital_address", "") or "",
        hospital_phone=seed.get("hospital_phone", "") or "",
        hospital_email=seed.get("hospital_email", "") or "",
        db_location="",  # already resolved
        admin_username=seed["admin_username"],
        admin_email=seed.get("admin_email") or f"{seed['admin_username']}@local",
        admin_password=password,
        admin_first_name=seed.get("admin_first_name") or "System",
        admin_last_name=seed.get("admin_last_name") or "Administrator",
        license_file_content="",
        backup_locations=backup_locations,
    )

    try:
        _init_database_and_seed(req, db_path)
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
                result = _store_license(content, db_path)
                if not result.get("stored"):
                    log.warning("License install failed: %s", result.get("error"))
            except Exception as e:
                log.warning("License install raised %s — operator can upload from Dashboard", e)


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
