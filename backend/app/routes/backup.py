"""
Backup management API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import tempfile
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter()


class BackupLocationsRequest(BaseModel):
    locations: List[str]


class DbMigrateRequest(BaseModel):
    new_folder: str


def _require_admin(user):
    if not any(r in user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/db-info")
async def get_db_info(current_user: User = Depends(get_current_user)):
    """Get current database file info: path, size, last modified, integrity."""
    _require_admin(current_user)
    import sqlite3
    from app.utils.config import get_configured_db_path

    db_path = get_configured_db_path()
    result = {"db_path": db_path, "file_size_mb": 0, "last_modified": None, "integrity": "unknown"}

    if os.path.isfile(db_path):
        stat = os.stat(db_path)
        result["file_size_mb"] = round(stat.st_size / (1024 * 1024), 2)
        from datetime import datetime
        result["last_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()

        try:
            conn = sqlite3.connect(db_path)
            check = conn.execute("PRAGMA integrity_check").fetchone()
            result["integrity"] = check[0] if check else "unknown"
            conn.close()
        except Exception as e:
            result["integrity"] = f"error: {e}"

    else:
        result["integrity"] = "file not found"

    return result


@router.post("/db-migrate")
async def migrate_database_location(
    data: DbMigrateRequest,
    current_user: User = Depends(get_current_user)
):
    """Move the database file to a new location using SQLite backup API."""
    _require_admin(current_user)
    import sqlite3
    from app.utils.config import get_configured_db_path, load_config, save_config

    new_folder = os.path.expanduser(data.new_folder.strip())
    if not new_folder:
        raise HTTPException(status_code=400, detail="New folder path is required")

    # Validate new folder
    try:
        os.makedirs(new_folder, exist_ok=True)
        test_file = os.path.join(new_folder, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except PermissionError:
        raise HTTPException(status_code=400, detail="Permission denied. Cannot write to this location.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

    old_path = get_configured_db_path()
    new_path = os.path.join(new_folder, "kthealth_erp.db")

    if os.path.abspath(old_path) == os.path.abspath(new_path):
        raise HTTPException(status_code=400, detail="New location is the same as current location")

    if not os.path.isfile(old_path):
        raise HTTPException(status_code=400, detail="Current database file not found")

    # Copy using SQLite backup API (safe while in use)
    try:
        source_conn = sqlite3.connect(old_path)
        dest_conn = sqlite3.connect(new_path)
        source_conn.backup(dest_conn)
        dest_conn.close()
        source_conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database copy failed: {e}")

    # Update config.json
    config = load_config()
    config["db_path"] = new_path
    save_config(config)

    # Reinitialize engine to use new path
    from config.database import reinitialize_engine
    reinitialize_engine()

    # Audit log
    try:
        from config.database import get_db
        from app.services.audit_service import log_action
        db = next(get_db())
        log_action(db, current_user, "migrate_database", "admin", "Database", None,
            f"Migrated database from {old_path} to {new_path}",
            details={"old_path": old_path, "new_path": new_path})
        db.close()
    except Exception:
        pass

    return {
        "message": "Database migrated successfully",
        "old_path": old_path,
        "new_path": new_path,
    }


@router.get("/system-info")
async def get_system_info(current_user: User = Depends(get_current_user)):
    """Get full system info: config, DB, uploads."""
    _require_admin(current_user)
    import sqlite3
    from app.utils.config import get_configured_db_path, load_config
    from app.utils.paths import get_uploads_dir

    config = load_config()
    db_path = get_configured_db_path()
    uploads_dir = get_uploads_dir()

    # DB info
    db_info = {"path": db_path, "size_mb": 0, "last_modified": None, "integrity": "unknown"}
    if os.path.isfile(db_path):
        stat = os.stat(db_path)
        db_info["size_mb"] = round(stat.st_size / (1024 * 1024), 2)
        from datetime import datetime
        db_info["last_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        try:
            conn = sqlite3.connect(db_path)
            check = conn.execute("PRAGMA integrity_check").fetchone()
            db_info["integrity"] = check[0] if check else "unknown"
            conn.close()
        except Exception as e:
            db_info["integrity"] = f"error: {e}"

    # Uploads info — also check which modules reference each file
    from sqlalchemy.orm import Session as _Sess
    from config.database import SessionLocal
    from app.models.hospital import Hospital
    from app.models.permissions import HospitalSettings

    try:
        _db: _Sess = SessionLocal()
        # Collect all image URLs referenced in config
        image_usage = {}  # url -> list of usage labels
        hospital = _db.query(Hospital).first()
        if hospital and hospital.logo_url:
            image_usage[hospital.logo_url] = image_usage.get(hospital.logo_url, [])
            image_usage[hospital.logo_url].append("Hospital Logo (Bills, Prescriptions)")

        for setting in _db.query(HospitalSettings).filter(
            HospitalSettings.setting_key.in_(["provider_logo", "signature_image"])
        ).all():
            if setting.setting_value:
                url = setting.setting_value
                module = setting.setting_category.replace("_config", "").capitalize()
                label = f"{module} Logo" if setting.setting_key == "provider_logo" else f"{module} Signature"
                image_usage[url] = image_usage.get(url, [])
                image_usage[url].append(label)
        _db.close()
    except Exception:
        image_usage = {}

    uploads = []
    if os.path.isdir(uploads_dir):
        for root, dirs, files in os.walk(uploads_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, uploads_dir)
                folder = os.path.dirname(rel_path) or "root"
                stat = os.stat(fpath)
                file_url = f"/uploads/{rel_path}"
                used_by = image_usage.get(file_url, [])
                uploads.append({
                    "name": fname,
                    "folder": folder,
                    "url": file_url,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "used_by": used_by,
                })

    return {
        "config": {
            "setup_complete": config.get("setup_complete", False),
            "hospital_name": config.get("hospital_name", ""),
            "db_path": config.get("db_path", ""),
            "backup_locations": config.get("backup_locations", []),
        },
        "database": db_info,
        "uploads": {
            "directory": uploads_dir,
            "files": uploads,
            "total_size_kb": round(sum(f["size_kb"] for f in uploads), 1),
        },
    }


@router.get("/locations")
async def get_backup_locations(current_user: User = Depends(get_current_user)):
    """Get configured backup locations."""
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import get_backup_locations
    return {"locations": get_backup_locations()}


@router.put("/locations")
async def update_backup_locations(
    data: BackupLocationsRequest,
    current_user: User = Depends(get_current_user),
):
    """Update backup locations list."""
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    import os
    from app.utils.config import load_config, save_config

    valid = []
    errors = []
    for loc in data.locations:
        loc = loc.strip()
        if not loc:
            continue
        expanded = os.path.expanduser(loc)
        try:
            os.makedirs(expanded, exist_ok=True)
            valid.append(expanded)
        except Exception as e:
            errors.append({"path": loc, "error": str(e)})

    config = load_config()
    config["backup_locations"] = valid
    save_config(config)

    return {"locations": valid, "errors": errors}


@router.post("/run")
async def run_backup_now(current_user: User = Depends(get_current_user)):
    """Run backup immediately to all configured locations."""
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import run_backup
    result = run_backup()

    if not result["results"]:
        raise HTTPException(
            status_code=400,
            detail="No backup locations configured. Add locations first.",
        )

    # Audit log
    try:
        from config.database import get_db
        from app.services.audit_service import log_action
        db = next(get_db())
        success_count = sum(1 for r in result["results"] if r["success"])
        log_action(db, current_user, "run_backup", "admin", "Backup", None,
            f"Ran database backup — {success_count}/{len(result['results'])} locations successful",
            details={"results": result["results"]})
        db.close()
    except Exception:
        pass

    return result


@router.get("/mirror-status")
async def get_mirror_backup_status(current_user: User = Depends(get_current_user)):
    """Get real-time mirror backup status, including per-location detail so the
    admin dashboard can show a green/red row per destination instead of a
    single global flag.
    """
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import get_mirror_status, get_per_location_status
    status = get_mirror_status()
    status["per_location"] = get_per_location_status()
    return status


@router.post("/mirror/start")
async def start_mirror(current_user: User = Depends(get_current_user)):
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import start_mirror_backup
    start_mirror_backup(interval_seconds=60)
    return {"message": "Mirror backup started"}


@router.post("/mirror/stop")
async def stop_mirror(current_user: User = Depends(get_current_user)):
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import stop_mirror_backup
    stop_mirror_backup()
    return {"message": "Mirror backup stopped"}


# ============================================================
# Scheduled Snapshot Backup
# ============================================================

class SnapshotConfigUpdate(BaseModel):
    interval_minutes: int = Field(default=30, ge=15, le=360)
    retention_hours: int = Field(default=72, ge=1, le=720)


@router.get("/snapshot-status")
async def get_snapshot_status(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    from app.utils.config import get_snapshot_status, get_snapshot_info, get_backup_locations
    status = get_snapshot_status()
    status["info"] = get_snapshot_info(get_backup_locations())
    return status


@router.post("/snapshot/start")
async def start_snapshots(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    from app.utils.config import start_snapshot_backup, load_config
    config = load_config()
    interval = config.get("snapshot_interval_minutes", 30)
    start_snapshot_backup(interval_minutes=interval)
    return {"message": f"Snapshot backup started (every {interval} min)"}


@router.post("/snapshot/stop")
async def stop_snapshots(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    from app.utils.config import stop_snapshot_backup
    stop_snapshot_backup()
    return {"message": "Snapshot backup stopped"}


@router.put("/snapshot-config")
async def update_snapshot_config(
    data: SnapshotConfigUpdate,
    current_user: User = Depends(get_current_user)
):
    _require_admin(current_user)
    from app.utils.config import load_config, save_config, stop_snapshot_backup, start_snapshot_backup, _snapshot_running

    config = load_config()
    config["snapshot_interval_minutes"] = data.interval_minutes
    config["snapshot_retention_hours"] = data.retention_hours
    save_config(config)

    # Restart if running to apply new interval
    if _snapshot_running:
        stop_snapshot_backup()
        import time
        time.sleep(0.5)
        start_snapshot_backup(interval_minutes=data.interval_minutes)

    return {"message": f"Snapshot config updated: every {data.interval_minutes} min, retain {data.retention_hours}h"}


# ============================================================
# Google Drive Backup
# ============================================================

@router.get("/gdrive-status")
async def get_gdrive_backup_status(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    from app.utils.config import get_gdrive_status
    return get_gdrive_status()


@router.post("/gdrive-backup-now")
async def trigger_gdrive_backup(current_user: User = Depends(get_current_user)):
    _require_admin(current_user)
    from app.utils.config import run_gdrive_backup
    try:
        run_gdrive_backup()
        from app.utils.config import get_gdrive_status
        status = get_gdrive_status()
        if status.get("last_error"):
            raise HTTPException(status_code=500, detail=status["last_error"])
        return {"message": "Google Drive backup completed"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Restore from Backup
# ============================================================

_restore_in_progress = False


class RestoreRequest(BaseModel):
    backup_path: str
    backup_type: str  # manual, snapshot, mirror
    # Set True only after the operator has acknowledged the machine-mismatch
    # prompt: the restored DB carries a license bound to another machine and
    # they intend to request a rebind afterwards.
    allow_machine_mismatch: bool = False


class RebindFromBackupRequest(BaseModel):
    backup_path: str


@router.get("/restore/list")
async def list_restore_points(current_user: User = Depends(get_current_user)):
    """List all available backup files that can be restored."""
    _require_admin(current_user)
    import datetime as dt
    from app.utils.config import get_backup_locations, get_configured_db_path, SNAPSHOT_FOLDER

    backup_locations = get_backup_locations()
    current_db = os.path.abspath(get_configured_db_path())
    restore_points = []

    for location in backup_locations:
        # Manual backups: kthealth_erp_backup_{timestamp}/kthealth_erp.db
        for entry in sorted(os.listdir(location), reverse=True) if os.path.isdir(location) else []:
            if entry.startswith("kthealth_erp_backup_"):
                db_file = os.path.join(location, entry, "kthealth_erp.db")
                if os.path.isfile(db_file) and os.path.abspath(db_file) != current_db:
                    has_uploads = os.path.isdir(os.path.join(location, entry, "uploads"))
                    stat = os.stat(db_file)
                    restore_points.append({
                        "type": "manual",
                        "path": db_file,
                        "folder": os.path.join(location, entry),
                        "filename": entry,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "has_uploads": has_uploads,
                    })

        # Snapshots: kthealth_erp_snapshots/snapshot_{timestamp}.db
        snap_dir = os.path.join(location, SNAPSHOT_FOLDER)
        if os.path.isdir(snap_dir):
            for fname in sorted(os.listdir(snap_dir), reverse=True):
                if fname.startswith("snapshot_") and fname.endswith(".db"):
                    fpath = os.path.join(snap_dir, fname)
                    if os.path.abspath(fpath) != current_db:
                        stat = os.stat(fpath)
                        restore_points.append({
                            "type": "snapshot",
                            "path": fpath,
                            "folder": snap_dir,
                            "filename": fname,
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "created": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "has_uploads": False,
                        })

        # Mirror: kthealth_erp_mirror/kthealth_erp.db
        mirror_db = os.path.join(location, "kthealth_erp_mirror", "kthealth_erp.db")
        if os.path.isfile(mirror_db) and os.path.abspath(mirror_db) != current_db:
            has_uploads = os.path.isdir(os.path.join(location, "kthealth_erp_mirror", "uploads"))
            stat = os.stat(mirror_db)
            restore_points.append({
                "type": "mirror",
                "path": mirror_db,
                "folder": os.path.join(location, "kthealth_erp_mirror"),
                "filename": "kthealth_erp.db (mirror)",
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "has_uploads": has_uploads,
            })

    # Sort by created date descending
    restore_points.sort(key=lambda r: r["created"], reverse=True)
    return {"restore_points": restore_points}


def _validate_backup_db_file(
    backup_path: str,
    current_db: str,
    allow_same_path: bool = False,
    allow_machine_mismatch: bool = False,
) -> None:
    """Raises HTTPException on any problem. Same checks as the original
    inline validation in /restore, plus a machine-binding pre-check so an
    admin can't accidentally swap in a DB whose license belongs to another
    machine (would leave the system in machine_mismatch after the swap).

    When ``allow_machine_mismatch`` is True the machine-binding block is
    downgraded from a hard error to a no-op — used when the operator has
    explicitly acknowledged they're migrating a DB from another machine and
    intends to request a license rebind afterwards. In that case the error
    carries a structured ``detail`` (``code == "license_machine_mismatch"``)
    so the frontend can offer the rebind / "restore anyway" choices instead
    of a dead-end message."""
    import sqlite3

    if not os.path.isfile(backup_path):
        raise HTTPException(status_code=400, detail="Backup file not found")
    if (not allow_same_path) and os.path.abspath(backup_path) == os.path.abspath(current_db):
        raise HTTPException(status_code=400, detail="Cannot restore from the active database file")
    if os.path.getsize(backup_path) == 0:
        raise HTTPException(status_code=400, detail="Backup file is empty")
    with open(backup_path, "rb") as f:
        header = f.read(16)
    if not header.startswith(b"SQLite format 3"):
        raise HTTPException(status_code=400, detail="File is not a valid SQLite database")
    try:
        conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                raise HTTPException(status_code=400, detail=f"Backup file integrity check failed: {result[0]}")
            # Sentinel: candidate DB must have a populated users table.
            try:
                cur = conn.execute("SELECT 1 FROM users LIMIT 1")
                if cur.fetchone() is None:
                    raise HTTPException(status_code=400, detail="Backup has no users — not a valid hospital DB.")
            except sqlite3.Error:
                raise HTTPException(status_code=400, detail="Backup is missing the 'users' table.")
            # Machine binding: refuse to restore a DB bound to another machine.
            try:
                row = conn.execute(
                    "SELECT raw_license_data FROM licenses ORDER BY id DESC LIMIT 1"
                ).fetchone()
            except sqlite3.Error:
                row = None
            if row and row[0] and not allow_machine_mismatch:
                from app.services.license_service import verify_license_machine_binding
                class _Stub:
                    pass
                stub = _Stub()
                stub.raw_license_data = row[0]
                ok, lic_mid, cur_mid = verify_license_machine_binding(stub)
                if not ok:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "license_machine_mismatch",
                            "message": (
                                "This backup's license is bound to a different machine "
                                f"(license machine {lic_mid or 'unknown'}, this machine "
                                f"{cur_mid}). Generate a rebind request so your vendor can "
                                "re-issue the license for this machine, or restore anyway "
                                "and rebind afterwards."
                            ),
                            "license_machine_id": lic_mid,
                            "current_machine_id": cur_mid,
                        },
                    )
        finally:
            conn.close()
    except HTTPException:
        raise
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"Cannot read backup file: {e}")


def _verify_restored_db(db_path: str) -> tuple[bool, str]:
    """Run the same checks against a freshly-restored DB. Returns (ok, reason)."""
    import sqlite3
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception as e:
        return False, f"Cannot open restored DB: {e}"
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if not row or row[0] != "ok":
            return False, f"Post-restore integrity check failed: {row[0] if row else 'no result'}"
        cur = conn.execute("SELECT 1 FROM users LIMIT 1")
        if cur.fetchone() is None:
            return False, "Restored DB has no users."
    except sqlite3.Error as e:
        return False, f"Post-restore probe failed: {e}"
    finally:
        conn.close()
    return True, ""


def _run_restore_from_path(backup_path: str, backup_type: str, current_user: User) -> dict:
    """Shared restore mechanics. Wraps the swap with maintenance mode so user
    writes don't race the swap; verifies the restored DB before declaring
    success; reverts from the pre-restore safety copy on failure.
    """
    import sqlite3
    import shutil
    import time
    import datetime as dt
    from app.utils.config import (
        get_configured_db_path, get_backup_locations,
        stop_mirror_backup, start_mirror_backup, get_mirror_status,
        stop_snapshot_backup, start_snapshot_backup, get_snapshot_status,
        load_config,
    )
    from app.utils.paths import get_uploads_dir
    from app.utils.backup_verify import verify_backup_artifact
    from app.middleware.maintenance import enable_maintenance_mode, disable_maintenance_mode

    current_db = get_configured_db_path()

    enable_maintenance_mode(
        f"Restoring from {backup_type} backup: {os.path.basename(backup_path)}"
    )

    mirror_was_running = get_mirror_status()["running"]
    snapshot_was_running = get_snapshot_status()["running"]
    if mirror_was_running:
        stop_mirror_backup()
    if snapshot_was_running:
        stop_snapshot_backup()
    # 2-second grace period for in-flight writes to drain.
    time.sleep(2)

    backup_locations = get_backup_locations()
    pre_restore_name = f"pre_restore_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    pre_restore_path: Optional[str] = None
    pre_restore_saved = False
    if backup_locations and os.path.isfile(current_db):
        pre_restore_dir = os.path.join(backup_locations[0], "kthealth_erp_pre_restore")
        try:
            os.makedirs(pre_restore_dir, exist_ok=True)
            pre_restore_path = os.path.join(pre_restore_dir, pre_restore_name)
            src = sqlite3.connect(current_db)
            dst = sqlite3.connect(pre_restore_path)
            src.backup(dst)
            dst.close()
            src.close()
            # Verify the safety copy before we touch anything.
            verify = verify_backup_artifact(pre_restore_path, full_check=True, source_db_path=current_db)
            if not verify["ok"]:
                raise RuntimeError(f"Pre-restore safety backup failed verification: {verify.get('error') or verify.get('integrity')}")
            pre_restore_saved = True
            _cleanup_old_pre_restore(pre_restore_dir, keep=5)
        except Exception as e:
            disable_maintenance_mode()
            raise HTTPException(status_code=500, detail=f"Failed to create pre-restore backup: {e}")

    # --- Swap ---
    try:
        src = sqlite3.connect(backup_path)
        dst = sqlite3.connect(current_db)
        src.backup(dst)
        dst.close()
        src.close()
    except Exception as e:
        disable_maintenance_mode()
        raise HTTPException(status_code=500, detail=f"Database restore failed: {e}")

    # --- Verify the restored DB before declaring success ---
    ok, reason = _verify_restored_db(current_db)
    if not ok:
        revert_failed = ""
        if pre_restore_saved and pre_restore_path and os.path.isfile(pre_restore_path):
            try:
                src = sqlite3.connect(pre_restore_path)
                dst = sqlite3.connect(current_db)
                src.backup(dst)
                dst.close()
                src.close()
            except Exception as rev_e:
                revert_failed = f" Revert also failed: {rev_e}"
        try:
            from app.services.backup_audit import record_event
            record_event(
                "restore_failed",
                f"Restore from {backup_type} aborted and reverted",
                details={"reason": reason, "backup_path": backup_path, "reverted": pre_restore_saved},
            )
        except Exception:
            pass
        disable_maintenance_mode()
        if mirror_was_running and backup_locations:
            start_mirror_backup(interval_seconds=60)
        if snapshot_was_running and backup_locations:
            snap_interval = load_config().get("snapshot_interval_minutes", 30)
            start_snapshot_backup(interval_minutes=snap_interval)
        raise HTTPException(
            status_code=500,
            detail=f"Restore aborted: {reason}. Reverted to previous DB.{revert_failed}",
        )

    # --- Restore uploads if available ---
    uploads_restored = False
    candidate_uploads = [
        os.path.join(os.path.dirname(backup_path), "uploads"),  # mirror / manual / folder-snapshot layout
    ]
    for backup_uploads in candidate_uploads:
        if os.path.isdir(backup_uploads):
            try:
                uploads_dir = get_uploads_dir()
                shutil.copytree(backup_uploads, uploads_dir, dirs_exist_ok=True)
                uploads_restored = True
                break
            except Exception:
                pass

    # --- Reinitialize engine + run migrations ---
    from config.database import reinitialize_engine
    reinitialize_engine()
    try:
        from migrate_patient_fields import migrate
        migrate()
    except Exception:
        pass

    # --- Restart background threads ---
    config = load_config()
    if mirror_was_running and backup_locations:
        start_mirror_backup(interval_seconds=60)
    if snapshot_was_running and backup_locations:
        snap_interval = config.get("snapshot_interval_minutes", 30)
        start_snapshot_backup(interval_minutes=snap_interval)

    # --- Audit log ---
    try:
        from config.database import get_db
        from app.services.audit_service import log_action
        db = next(get_db())
        log_action(db, current_user, "restore_database", "admin", "Database", None,
            f"Restored database from {backup_type} backup: {os.path.basename(backup_path)}",
            details={"backup_path": backup_path, "backup_type": backup_type,
                     "pre_restore_backup": pre_restore_name if pre_restore_saved else None})
        db.close()
    except Exception:
        pass

    disable_maintenance_mode()

    return {
        "message": "Database restored successfully",
        "backup_used": os.path.basename(backup_path),
        "backup_type": backup_type,
        "pre_restore_backup": pre_restore_name if pre_restore_saved else None,
        "uploads_restored": uploads_restored,
        "verified": True,
        "force_logout": True,
    }


def _cleanup_old_pre_restore(pre_restore_dir: str, keep: int = 5) -> None:
    """Keep only the most recent N pre-restore snapshots."""
    try:
        entries = []
        for fname in os.listdir(pre_restore_dir):
            if not fname.startswith("pre_restore_") or not fname.endswith(".db"):
                continue
            fpath = os.path.join(pre_restore_dir, fname)
            try:
                entries.append((os.path.getmtime(fpath), fpath))
            except OSError:
                continue
        entries.sort(reverse=True)
        for _mtime, fpath in entries[keep:]:
            try:
                os.remove(fpath)
            except OSError:
                pass
            # Also remove sibling sidecar if present.
            try:
                os.remove(fpath + ".verified.json")
            except OSError:
                pass
    except Exception:
        pass


def _read_backup_license(backup_path: str) -> Optional[dict]:
    """Read the newest license row (raw signature + identity columns) out of a
    backup .db file. Read-only; returns None when the backup has no license."""
    import sqlite3
    try:
        conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    except Exception:
        return None
    try:
        row = conn.execute(
            "SELECT raw_license_data, license_id, hospital_id, hospital_name "
            "FROM licenses ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    return {
        "raw_license_data": row[0],
        "license_id": row[1],
        "hospital_id": row[2],
        "hospital_name": row[3],
    }


def _rebind_response_from_backup(backup_path: str, requested_by: str) -> Response:
    """Build a downloadable .rebind.json from the license stored inside a
    backup .db. This is what makes the 'DB from another machine' edge case
    recoverable: the operator can generate the rebind request straight from
    the backup, without first having to swap it in (which the machine-binding
    guard would otherwise block)."""
    import json as _json
    from app.services.license_service import build_rebind_request_payload

    lic = _read_backup_license(backup_path)
    if not lic:
        raise HTTPException(
            status_code=400,
            detail="This backup does not contain a license, so there is nothing to rebind.",
        )
    try:
        payload = build_rebind_request_payload(
            lic["raw_license_data"],
            license_id=lic["license_id"],
            hospital_id=lic["hospital_id"],
            hospital_name=lic["hospital_name"],
            requested_by=requested_by,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not build rebind request: {e}")

    if payload.get("old_machine_id") and payload["old_machine_id"] == payload["new_machine_id"]:
        raise HTTPException(
            status_code=400,
            detail="This backup's license already matches this machine — no rebind needed.",
        )

    safe_name = (lic.get("hospital_name") or "kthealth").replace(" ", "_")
    filename = f"{safe_name}_rebind_{payload['new_machine_id']}.rebind.json"
    return Response(
        content=_json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_database(
    data: RestoreRequest,
    current_user: User = Depends(get_current_user)
):
    """Restore database from a backup file."""
    _require_admin(current_user)
    from app.utils.config import get_configured_db_path

    global _restore_in_progress
    if _restore_in_progress:
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    backup_path = data.backup_path
    current_db = get_configured_db_path()
    _validate_backup_db_file(
        backup_path, current_db, allow_machine_mismatch=data.allow_machine_mismatch
    )

    try:
        return _run_restore_from_path(backup_path, data.backup_type, current_user)
    finally:
        _restore_in_progress = False


@router.post("/restore/rebind-request")
async def rebind_request_from_backup(
    data: RebindFromBackupRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate a .rebind.json for the license inside a listed backup file,
    without restoring it. Lets the operator kick off a rebind for a DB that
    came from another machine."""
    _require_admin(current_user)
    if not os.path.isfile(data.backup_path):
        raise HTTPException(status_code=400, detail="Backup file not found")
    return _rebind_response_from_backup(data.backup_path, current_user.username)


@router.post("/restore-upload")
async def restore_database_from_upload(
    file: UploadFile = File(...),
    allow_machine_mismatch: bool = Form(False),
    current_user: User = Depends(get_current_user),
):
    """Restore the database from an uploaded .db file (e.g. one received over
    USB / cloud sync). Same safety steps as /restore: validates the upload,
    snapshots the current DB to pre-restore, then swaps it in.

    ``allow_machine_mismatch`` bypasses the license machine-binding guard for
    the documented 'migrating a DB from another machine' case; the operator is
    expected to request a rebind afterwards."""
    _require_admin(current_user)
    from app.utils.config import get_configured_db_path

    global _restore_in_progress
    if _restore_in_progress:
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    # Stream the upload to a temp file so we can validate it on disk.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="kthealth_upload_")
    os.close(tmp_fd)
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        current_db = get_configured_db_path()
        _validate_backup_db_file(
            tmp_path, current_db, allow_same_path=True,
            allow_machine_mismatch=allow_machine_mismatch,
        )

        _restore_in_progress = True
        try:
            return _run_restore_from_path(tmp_path, "upload", current_user)
        finally:
            _restore_in_progress = False
    finally:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


@router.post("/restore-upload/rebind-request")
async def rebind_request_from_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Generate a .rebind.json for the license inside an uploaded .db file,
    without restoring it. Companion to /restore-upload for the case where the
    uploaded DB is bound to another machine."""
    _require_admin(current_user)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix="kthealth_rebind_")
    os.close(tmp_fd)
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

        with open(tmp_path, "rb") as f:
            if not f.read(16).startswith(b"SQLite format 3"):
                raise HTTPException(status_code=400, detail="File is not a valid SQLite database")

        return _rebind_response_from_backup(tmp_path, current_user.username)
    finally:
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


# ============================================================
# Phase 1 — health endpoint
# ============================================================

@router.get("/health")
async def backup_health(current_user: User = Depends(get_current_user)):
    """Aggregate backup health for the dashboard banner."""
    _require_admin(current_user)
    from app.services.backup_health import compute_backup_health
    return compute_backup_health()


@router.get("/health/public")
async def backup_health_public():
    """Same payload as /health but without auth. Returns minimal info so the
    pre-login banner / health checks have something to read. Sensitive fields
    are stripped."""
    from app.services.backup_health import compute_backup_health
    full = compute_backup_health()
    return {
        "status": full["status"],
        "message": full["message"],
        "locations_configured": full["locations_configured"],
        "locations_healthy": full["locations_healthy"],
    }


# ============================================================
# Phase 2 — disk usage / distinct device check + retention
# ============================================================

def _path_device_id(path: str) -> str:
    """Return a deterministic identifier for the device hosting `path`.

    On POSIX we use `st_dev` from stat; on Windows we look up the volume
    serial number via ctypes. Returned as a string so it's directly
    comparable across locations.
    """
    import platform
    try:
        if platform.system() == "Windows":
            import ctypes
            from ctypes import wintypes
            drive = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
            serial = wintypes.DWORD()
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(drive),
                None, 0,
                ctypes.byref(serial),
                None, None, None, 0,
            )
            return f"win-volume-{serial.value}"
        return f"posix-st_dev-{os.stat(path).st_dev}"
    except Exception:
        return ""


class LocationCheckRequest(BaseModel):
    path: str


@router.post("/locations/check")
async def check_backup_location(
    data: LocationCheckRequest,
    current_user: User = Depends(get_current_user),
):
    """Pre-flight check for a candidate backup location.

    Verifies the path is writable, has enough free space relative to the
    current DB size, and warns if it's on the same physical device as the
    DB or any existing backup location.
    """
    _require_admin(current_user)
    import shutil as _sh
    from app.utils.config import get_configured_db_path, load_config

    raw = (data.path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Path is required")
    expanded = os.path.expanduser(raw)

    try:
        os.makedirs(expanded, exist_ok=True)
        test_file = os.path.join(expanded, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except PermissionError:
        raise HTTPException(status_code=400, detail="Permission denied — cannot write to this location.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid path: {e}")

    db_path = get_configured_db_path()
    db_size = os.path.getsize(db_path) if os.path.isfile(db_path) else 0

    try:
        usage = _sh.disk_usage(expanded)
        free_bytes = usage.free
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read disk usage: {e}")

    warnings: list = []
    errors: list = []
    if db_size and free_bytes < db_size * 3:
        errors.append(
            f"Insufficient free space ({free_bytes // (1024*1024)} MB free, "
            f"need at least {db_size * 3 // (1024*1024)} MB)."
        )
    elif db_size and free_bytes < db_size * 10:
        warnings.append(
            f"Tight free space ({free_bytes // (1024*1024)} MB) — backups will "
            f"fill this disk quickly."
        )

    candidate_dev = _path_device_id(expanded)
    db_dev = _path_device_id(os.path.dirname(db_path) or ".") if os.path.isfile(db_path) else ""
    if candidate_dev and db_dev and candidate_dev == db_dev:
        warnings.append(
            "This location is on the same physical device as the live database. "
            "A single disk failure would lose both copies."
        )

    config = load_config()
    for existing in config.get("backup_locations", []):
        if os.path.abspath(existing) == os.path.abspath(expanded):
            errors.append("This location is already configured.")
            continue
        try:
            existing_dev = _path_device_id(existing)
        except Exception:
            existing_dev = ""
        if candidate_dev and existing_dev and candidate_dev == existing_dev:
            warnings.append(
                f"Same physical device as existing backup location '{existing}'."
            )

    return {
        "valid": len(errors) == 0,
        "resolved_path": expanded,
        "free_mb": free_bytes // (1024 * 1024),
        "db_size_mb": db_size // (1024 * 1024),
        "device_id": candidate_dev,
        "warnings": warnings,
        "errors": errors,
    }


class RetentionConfigRequest(BaseModel):
    snapshot_retention_days: int = Field(default=7, ge=1, le=365)
    snapshot_interval_minutes: int = Field(default=30, ge=15, le=360)


@router.put("/retention-config")
async def update_retention_config(
    data: RetentionConfigRequest,
    current_user: User = Depends(get_current_user),
):
    """Single endpoint for snapshot interval + retention. Replaces the old
    `snapshot_retention_hours` semantics with days."""
    _require_admin(current_user)
    from app.utils.config import (
        load_config, save_config, stop_snapshot_backup,
        start_snapshot_backup, _snapshot_running,
    )
    from app.services.backup_audit import record_event

    config = load_config()
    config["snapshot_interval_minutes"] = data.snapshot_interval_minutes
    config["snapshot_retention_days"] = data.snapshot_retention_days
    # Drop legacy key once we've migrated it.
    config.pop("snapshot_retention_hours", None)
    save_config(config)

    if _snapshot_running:
        stop_snapshot_backup()
        import time as _t
        _t.sleep(0.5)
        start_snapshot_backup(interval_minutes=data.snapshot_interval_minutes)

    record_event(
        "backup_retention_updated",
        f"Snapshot config: every {data.snapshot_interval_minutes} min, retain {data.snapshot_retention_days} days",
        details={"interval_minutes": data.snapshot_interval_minutes, "retention_days": data.snapshot_retention_days},
    )

    return {
        "message": "Retention config updated",
        "snapshot_interval_minutes": data.snapshot_interval_minutes,
        "snapshot_retention_days": data.snapshot_retention_days,
    }


# ============================================================
# Phase 2 — automatic test-restore
# ============================================================

@router.post("/test-restore")
async def run_test_restore(current_user: User = Depends(get_current_user)):
    """Run an on-demand test-restore: copy the most recent verified backup
    into a tempfile, run a full integrity check, and verify the users table
    is populated. Does NOT touch the live DB."""
    _require_admin(current_user)
    from app.utils.config import get_backup_locations, SNAPSHOT_FOLDER
    import sqlite3
    import shutil as _sh
    import tempfile as _tf

    backup_locations = get_backup_locations()
    if not backup_locations:
        raise HTTPException(status_code=400, detail="No backup locations configured.")

    candidates: list = []
    for location in backup_locations:
        mirror_db = os.path.join(location, "kthealth_erp_mirror", "kthealth_erp.db")
        if os.path.isfile(mirror_db):
            candidates.append(("mirror", mirror_db))
        snap_root = os.path.join(location, SNAPSHOT_FOLDER)
        if os.path.isdir(snap_root):
            entries = sorted(
                [e for e in os.listdir(snap_root) if e.startswith("snapshot_")],
                reverse=True,
            )
            for entry in entries:
                entry_path = os.path.join(snap_root, entry)
                if os.path.isdir(entry_path):
                    snap_db = os.path.join(entry_path, "kthealth_erp.db")
                    if os.path.isfile(snap_db):
                        candidates.append(("snapshot", snap_db))
                        break
                elif entry.endswith(".db") and os.path.isfile(entry_path):
                    candidates.append(("snapshot-legacy", entry_path))
                    break

    if not candidates:
        raise HTTPException(status_code=400, detail="No backup files found at any configured location.")

    results = []
    for kind, src_path in candidates:
        tmp = _tf.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            _sh.copy2(src_path, tmp.name)
            ok, reason = _verify_restored_db(tmp.name)
            results.append({"type": kind, "source": src_path, "ok": ok, "reason": reason or ""})
        except Exception as e:
            results.append({"type": kind, "source": src_path, "ok": False, "reason": str(e)})
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass

    all_ok = all(r["ok"] for r in results)
    from app.services.backup_audit import record_event
    record_event(
        "backup_test_restore",
        f"Test-restore: {sum(r['ok'] for r in results)}/{len(results)} backups passed",
        details={"results": results},
    )

    # Persist last result for the dashboard
    try:
        from config.database import SessionLocal
        from app.models.system import SystemSettings
        import json as _json
        import datetime as _dt
        db = SessionLocal()
        try:
            row = db.query(SystemSettings).filter(SystemSettings.setting_key == "backup_test_results").first()
            payload = _json.dumps({
                "last_run": _dt.datetime.now().isoformat(),
                "all_ok": all_ok,
                "results": results,
            })
            if row:
                row.setting_value = payload
                row.setting_type = "json"
            else:
                db.add(SystemSettings(
                    setting_key="backup_test_results",
                    setting_value=payload,
                    setting_type="json",
                    description="Latest automated backup test-restore results.",
                ))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass

    return {"all_ok": all_ok, "results": results, "tested": len(results)}


@router.get("/test-restore/last")
async def get_last_test_restore(current_user: User = Depends(get_current_user)):
    """Read the most recent stored test-restore results."""
    _require_admin(current_user)
    try:
        from config.database import SessionLocal
        from app.models.system import SystemSettings
        import json as _json
        db = SessionLocal()
        try:
            row = db.query(SystemSettings).filter(SystemSettings.setting_key == "backup_test_results").first()
            if not row or not row.setting_value:
                return {"last_run": None, "all_ok": None, "results": []}
            return _json.loads(row.setting_value)
        finally:
            db.close()
    except Exception as e:
        return {"last_run": None, "all_ok": None, "results": [], "error": str(e)}


@router.get("/maintenance")
async def get_maintenance_state_endpoint(current_user: User = Depends(get_current_user)):
    """Surface the current maintenance flag — used by the frontend
    503-handler to know whether the modal should auto-dismiss."""
    _require_admin(current_user)
    from app.middleware.maintenance import get_maintenance_state
    return get_maintenance_state()


# ============================================================
# Folder picker / path validator (used by BackupManagement)
# ============================================================

@router.get("/browse-folder")
async def browse_folder():
    """Open a native OS folder picker dialog and return the selected path.
    No auth: this is used by the BackupManagement page; doesn't touch any data."""
    import subprocess
    import platform

    folder = ""
    try:
        if platform.system() == "Darwin":
            script = (
                'tell application "Finder"\n'
                '  activate\n'
                'end tell\n'
                'set theFolder to choose folder with prompt "Select Folder"\n'
                'return POSIX path of theFolder'
            )
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                folder = proc.stdout.strip().rstrip("/")
        elif platform.system() == "Windows":
            ps_script = (
                'Add-Type -AssemblyName System.Windows.Forms; '
                '[System.Windows.Forms.Application]::EnableVisualStyles(); '
                '$top = New-Object System.Windows.Forms.Form; '
                '$top.TopMost = $true; '
                '$top.MinimizeBox = $false; '
                '$top.MaximizeBox = $false; '
                '$top.Width = 0; $top.Height = 0; '
                '$top.StartPosition = "Manual"; '
                '$top.Location = New-Object System.Drawing.Point(-1000,-1000); '
                '$top.Show(); $top.BringToFront(); '
                '$f = New-Object System.Windows.Forms.FolderBrowserDialog; '
                '$f.Description = "Select Folder"; '
                '$f.ShowNewFolderButton = $true; '
                '$result = $f.ShowDialog($top); '
                '$top.Close(); '
                'if ($result -eq [System.Windows.Forms.DialogResult]::OK) { '
                '  $f.SelectedPath '
                '}'
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                folder = proc.stdout.strip()
        else:
            for cmd in [
                ["zenity", "--file-selection", "--directory", "--title=Select Folder"],
                ["kdialog", "--getexistingdirectory", "."],
            ]:
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        folder = proc.stdout.strip()
                        break
                except FileNotFoundError:
                    continue
    except (subprocess.TimeoutExpired, Exception):
        pass

    return {"path": folder}


@router.post("/validate-path")
async def validate_path(data: dict):
    """Validate that a directory path exists and is writable."""
    path = (data.get("path") or "").strip()
    if not path:
        return {"valid": False, "message": "Path is empty"}

    path = os.path.expanduser(path)
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return {"valid": True, "message": "Path is valid and writable", "resolved_path": path}
    except PermissionError:
        return {"valid": False, "message": "Permission denied. Cannot write to this location."}
    except Exception as e:
        return {"valid": False, "message": str(e)}
