from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from config.database import get_db
from app.models.user import User
from app.models.hospital import Hospital
from app.utils.dependencies import get_current_user
from app.services.license_service import (
    get_license_status,
    upload_license,
    inspect_license_file,
    get_current_license,
)
from app.middleware.license_middleware import invalidate_license_cache

router = APIRouter()


@router.get("/machine-id")
async def get_machine_id_info():
    """Get this machine's unique ID for license binding. No auth required (needed before license upload)."""
    from app.utils.machine_id import get_machine_id_full
    return get_machine_id_full()


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


@router.get("/rebind-request")
async def generate_rebind_request(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build a self-service rebind request the operator can send to the vendor.

    The vendor's License Manager can verify the included signature proof
    against the original license, then re-issue a new .lic bound to the new
    machine ID without manual data entry. This is the fix for the "we moved
    the .exe to a new server and now the .lic is rejected" pain.
    """
    _require_admin(current_user)

    import json as _json
    from app.services.license_service import build_rebind_request_payload

    license_record = get_current_license(db)
    if not license_record:
        raise HTTPException(
            status_code=400,
            detail="No license is currently installed. Rebind requests can only be generated when an existing license is present.",
        )
    if not license_record.raw_license_data:
        raise HTTPException(
            status_code=400,
            detail="The current license has no stored signature data. Re-upload the original .lic first.",
        )

    request_payload = build_rebind_request_payload(
        license_record.raw_license_data,
        license_id=license_record.license_id,
        hospital_id=license_record.hospital_id,
        hospital_name=license_record.hospital_name,
        requested_by=current_user.username,
    )
    new_machine_id = request_payload["new_machine_id"]
    old_machine_id = request_payload["old_machine_id"]

    if old_machine_id and old_machine_id == new_machine_id:
        raise HTTPException(
            status_code=400,
            detail="This machine already matches the licensed machine ID — no rebind needed.",
        )

    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "generate_rebind_request", "admin", "License",
                   license_record.id,
                   f"Generated rebind request from {old_machine_id or '(unknown)'} -> {new_machine_id}",
                   details=request_payload)
    except Exception:
        pass

    safe_name = (license_record.hospital_name or "kthealth").replace(" ", "_")
    filename = f"{safe_name}_rebind_{new_machine_id}.rebind.json"
    body = _json.dumps(request_payload, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/validate")
async def validate_license_file(file: UploadFile = File(...)):
    """Dry-run validate a .lic file. Reports signature validity, license
    metadata, and whether the machine ID matches THIS machine — without
    persisting anything. Safe to call before login (used by the setup wizard)
    and before clicking "Apply" on the License Management page.
    """
    content = await file.read()
    try:
        file_content = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="License file is not valid text/UTF-8")
    return inspect_license_file(file_content)


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
