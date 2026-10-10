"""WhatsApp document sending. Document kinds live in the service registry."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.whatsapp import WhatsAppMessage
from app.services.audit_service import log_action
from app.services.license_service import license_allows_whatsapp
from app.services.whatsapp.media import resolve
from app.services.whatsapp.registry import get_document_kind, list_document_kinds
from app.services.whatsapp.sender import SendInProgress, send_prepared_document
from app.services.whatsapp.settings import (
    WhatsAppNotReady,
    public_settings,
    require_ready,
    update_settings,
)
from app.utils.dependencies import get_current_user, get_db, require_hospital_admin_or_above

import app.services.whatsapp.providers  # noqa: F401 — registers built-in document kinds

router = APIRouter()


class WhatsAppSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    auth_key: Optional[str] = None
    integrated_number: Optional[str] = None
    public_base_url: Optional[str] = None
    template_invoice: Optional[str] = None
    template_lab_report: Optional[str] = None
    template_prescription: Optional[str] = None
    template_discharge: Optional[str] = None


class SendDocumentRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=50)
    resource_id: str = Field(..., min_length=1, max_length=200)
    phone: Optional[str] = None
    include_header: Optional[bool] = None


def _raise_not_ready(exc: WhatsAppNotReady):
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/status")
def whatsapp_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    licensed = license_allows_whatsapp(db)
    settings = public_settings(db)
    return {
        "licensed": licensed,
        "enabled": bool(licensed and settings["enabled"]),
        "configured": bool(
            licensed
            and settings["enabled"]
            and settings["auth_key_set"]
            and settings["integrated_number"]
            and settings["public_base_url"]
        ),
        "kinds": list_document_kinds(),
    }


@router.get("/settings")
def get_whatsapp_settings(
    current_user: User = Depends(require_hospital_admin_or_above),
    db: Session = Depends(get_db),
):
    settings = public_settings(db)
    settings["licensed"] = license_allows_whatsapp(db)
    settings["recent"] = _recent(db, current_user.hospital_id)
    return settings


@router.put("/settings")
def put_whatsapp_settings(
    payload: WhatsAppSettingsUpdate,
    request: Request,
    current_user: User = Depends(require_hospital_admin_or_above),
    db: Session = Depends(get_db),
):
    if not license_allows_whatsapp(db):
        raise HTTPException(status_code=403, detail="WhatsApp is not included in this hospital's license.")
    try:
        saved = update_settings(db, payload.model_dump(), current_user.id)
    except WhatsAppNotReady as exc:
        _raise_not_ready(exc)
    log_action(
        db, current_user, "update_whatsapp_settings", "communications", "HospitalSettings",
        current_user.hospital_id,
        "Updated WhatsApp settings",
        ip_address=request.client.host if request.client else "",
        details={
            "enabled": saved["enabled"],
            "auth_key_set": saved["auth_key_set"],
            "integrated_number": saved["integrated_number"],
            "public_base_url": saved["public_base_url"],
        },
    )
    saved["licensed"] = True
    saved["recent"] = _recent(db, current_user.hospital_id)
    return saved


@router.get("/documents/defaults")
def document_defaults(
    kind: str,
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not license_allows_whatsapp(db):
        raise HTTPException(status_code=403, detail="WhatsApp is not included in this hospital's license.")
    document_kind = get_document_kind(kind)
    if document_kind is None:
        raise HTTPException(status_code=404, detail=f"WhatsApp is not set up for '{kind}'.")
    phone = ""
    if document_kind.suggest_phone:
        try:
            phone = document_kind.suggest_phone(db, current_user, resource_id) or ""
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document id.")
    return {"kind": kind, "resource_id": resource_id, "phone": phone}


@router.post("/documents")
def send_document(
    payload: SendDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document_kind = get_document_kind(payload.kind)
    if document_kind is None:
        raise HTTPException(status_code=404, detail=f"WhatsApp is not set up for '{payload.kind}'.")
    try:
        require_ready(db, document_kind.template_family)
        document = document_kind.load(db, current_user, payload.resource_id, payload.include_header)
        message = send_prepared_document(
            db,
            current_user,
            kind=payload.kind,
            document=document,
            phone=payload.phone or document.phone,
        )
    except WhatsAppNotReady as exc:
        _raise_not_ready(exc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document id.")
    except SendInProgress:
        raise HTTPException(status_code=429, detail="That document was just sent. Wait a few seconds before sending it again.")
    return {
        "id": message.id,
        "status": message.status,
        "phone": message.phone,
        "provider_request_id": message.provider_request_id,
    }


@router.get("/media/{token}")
def fetch_media(token: str):
    """Public to MSG91. The unguessable token is the authorization."""
    path = resolve(token)
    if not path:
        raise HTTPException(status_code=404, detail="This file is no longer available.")
    return FileResponse(path, media_type="application/pdf", filename="document.pdf")


def _recent(db: Session, hospital_id: int | None, limit: int = 20) -> list[dict]:
    query = db.query(WhatsAppMessage)
    if hospital_id:
        query = query.filter(WhatsAppMessage.hospital_id == hospital_id)
    rows = query.order_by(WhatsAppMessage.id.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "phone": row.phone,
            "status": row.status,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
