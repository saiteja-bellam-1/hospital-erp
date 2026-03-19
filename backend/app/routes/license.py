from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel

from config.database import get_db
from app.models.user import User
from app.models.hospital import Hospital
from app.utils.dependencies import get_current_user
from app.services.license_service import get_license_status, upload_license
from app.middleware.license_middleware import invalidate_license_cache

router = APIRouter()


def _require_admin(current_user: User):
    allowed = ["super_admin", "hospital_admin"]
    if not any(r in current_user.role_names for r in allowed):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/status")
async def license_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    return get_license_status(db)


@router.get("/status/public")
async def license_status_public(db: Session = Depends(get_db)):
    """Minimal license status + hospital info for login page — no auth required."""
    status_info = get_license_status(db)

    # Get hospital info
    hospital = db.query(Hospital).first()
    hospital_info = None
    if hospital:
        hospital_info = {
            "id": hospital.id,
            "hospital_id": hospital.hospital_id,
            "name": hospital.name,
        }

    return {
        "status": status_info["status"],
        "message": status_info["message"],
        "days_remaining": status_info["days_remaining"],
        "hospital": hospital_info,
    }


@router.post("/upload")
async def upload_license_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    content = await file.read()
    file_content = content.decode("utf-8")

    try:
        result = upload_license(db, file_content, uploaded_by=current_user.id)
        invalidate_license_cache()
        return {"message": "License uploaded successfully", "license": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"License upload error: {str(e)}")
