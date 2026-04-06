"""
Backup management API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
import os
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
    """Get real-time mirror backup status."""
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.config import get_mirror_status
    return get_mirror_status()


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
