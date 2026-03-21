"""
Backup management API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter()


class BackupLocationsRequest(BaseModel):
    locations: List[str]


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
