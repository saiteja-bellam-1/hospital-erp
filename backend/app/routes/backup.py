"""
Backup management API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import List
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


def _validate_backup_db_file(backup_path: str, current_db: str, allow_same_path: bool = False) -> None:
    """Raises HTTPException on any problem. Same checks as the original
    inline validation in /restore."""
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
        conn = sqlite3.connect(backup_path)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result[0] != "ok":
            raise HTTPException(status_code=400, detail=f"Backup file integrity check failed: {result[0]}")
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"Cannot read backup file: {e}")


def _run_restore_from_path(backup_path: str, backup_type: str, current_user: User) -> dict:
    """Shared restore mechanics used by both /restore (path-based) and
    /restore-upload (multipart upload). Caller must have already passed
    `_validate_backup_db_file`."""
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

    current_db = get_configured_db_path()

    # --- 1. Pause background threads ---
    mirror_was_running = get_mirror_status()["running"]
    snapshot_was_running = get_snapshot_status()["running"]
    if mirror_was_running:
        stop_mirror_backup()
    if snapshot_was_running:
        stop_snapshot_backup()
    time.sleep(1)

    # --- 2. Pre-restore safety backup ---
    backup_locations = get_backup_locations()
    pre_restore_name = f"pre_restore_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
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
            pre_restore_saved = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create pre-restore backup: {e}")

    # --- 3. Restore DB using SQLite backup API ---
    try:
        src = sqlite3.connect(backup_path)
        dst = sqlite3.connect(current_db)
        src.backup(dst)
        dst.close()
        src.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database restore failed: {e}")

    # --- 4. Restore uploads if available ---
    uploads_restored = False
    backup_uploads = os.path.join(os.path.dirname(backup_path), "uploads")
    if os.path.isdir(backup_uploads):
        try:
            uploads_dir = get_uploads_dir()
            shutil.copytree(backup_uploads, uploads_dir, dirs_exist_ok=True)
            uploads_restored = True
        except Exception:
            pass

    # --- 5. Reinitialize engine + run migrations ---
    from config.database import reinitialize_engine
    reinitialize_engine()
    try:
        from migrate_patient_fields import migrate
        migrate()
    except Exception:
        pass

    # --- 6. Restart background threads ---
    config = load_config()
    if mirror_was_running and backup_locations:
        start_mirror_backup(interval_seconds=60)
    if snapshot_was_running and backup_locations:
        snap_interval = config.get("snapshot_interval_minutes", 30)
        start_snapshot_backup(interval_minutes=snap_interval)

    # --- 7. Audit log ---
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

    return {
        "message": "Database restored successfully",
        "backup_used": os.path.basename(backup_path),
        "backup_type": backup_type,
        "pre_restore_backup": pre_restore_name if pre_restore_saved else None,
        "uploads_restored": uploads_restored,
        "force_logout": True,
    }


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
    _validate_backup_db_file(backup_path, current_db)

    try:
        return _run_restore_from_path(backup_path, data.backup_type, current_user)
    finally:
        _restore_in_progress = False


@router.post("/restore-upload")
async def restore_database_from_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Restore the database from an uploaded .db file (e.g. one received over
    USB / cloud sync). Same safety steps as /restore: validates the upload,
    snapshots the current DB to pre-restore, then swaps it in."""
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
        _validate_backup_db_file(tmp_path, current_db, allow_same_path=True)

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
