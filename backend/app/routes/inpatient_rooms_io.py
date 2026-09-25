"""Inpatient room catalog import/export routes (included under /api/inpatient)."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List

from app.models.hospital import Hospital
from app.models.user import User
from app.services.audit_service import log_action
from app.services.room_import import (
    build_rooms_template,
    export_rooms_xlsx,
    import_rooms_workbook,
)
from app.utils.auth import Modules
from app.utils.dependencies import require_feature_permission
from config.database import get_db

router = APIRouter()


class RoomImportRowError(BaseModel):
    sheet: str = ""
    row: int = 0
    message: str


class RoomImportPreviewRow(BaseModel):
    row: int = 0
    key: str = ""
    name: str = ""
    status: str
    message: str = ""
    sheet: str = ""


class RoomImportSummary(BaseModel):
    dry_run: bool
    total_rows: int
    created: int
    updated: int
    skipped: int
    created_beds: int = 0
    error_count: int
    errors: List[RoomImportRowError] = []
    preview: List[RoomImportPreviewRow] = []


def _xlsx_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _hospital_id(db: Session, current_user: User) -> int:
    if current_user.hospital_id:
        return current_user.hospital_id
    hospital = db.query(Hospital).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not configured")
    return hospital.id


@router.get("/rooms/import/template")
async def download_rooms_import_template(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
):
    """Download a ready-to-fill Rooms + Beds workbook."""
    return _xlsx_response(build_rooms_template(), "rooms_import_template.xlsx")


@router.get("/rooms/export/xlsx")
async def export_rooms_catalog(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Export active rooms in the same workbook format accepted by import."""
    return _xlsx_response(export_rooms_xlsx(db, _hospital_id(db, current_user)), "rooms_export.xlsx")


@router.post("/rooms/import", response_model=RoomImportSummary)
async def import_rooms(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
    db: Session = Depends(get_db),
):
    """Bulk-import rooms (and optional beds) from .xlsx or .csv.

    Occupancy is never written. ``dry_run=True`` previews without committing.
    ``on_duplicate`` is ``skip`` (default) or ``update`` for existing room_number.
    """
    if on_duplicate not in ("skip", "update"):
        on_duplicate = "skip"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    hospital_id = _hospital_id(db, current_user)
    try:
        summary = import_rooms_workbook(
            db, hospital_id, content, file.filename or "",
            dry_run=dry_run, on_duplicate=on_duplicate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")

    if dry_run:
        db.rollback()
    else:
        db.commit()
        try:
            log_action(
                db, current_user, "import_rooms", "inpatient", "Room", None,
                description=(
                    f"Imported rooms: {summary['created']} created, "
                    f"{summary['updated']} updated, {summary['skipped']} skipped, "
                    f"{summary['created_beds']} beds added"
                ),
                details={
                    "created": summary["created"],
                    "updated": summary["updated"],
                    "skipped": summary["skipped"],
                    "created_beds": summary["created_beds"],
                    "error_count": summary["error_count"],
                },
            )
        except Exception:
            pass
    return summary
