"""WhatsApp (via Web sidecar) — admin controls and staff-triggered sends."""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.user import User
from app.services import whatsapp_service as wa
from app.services.audit_service import log_action
from app.utils.dependencies import get_current_user, require_hospital_admin_or_above
from config.database import get_db

router = APIRouter()

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES = 5
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg"}


class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    default_country_code: Optional[str] = None
    templates: Optional[dict] = None


@router.get("/status")
def status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lightweight flag for the UI: show WhatsApp buttons only when enabled + linked."""
    enabled = wa.is_enabled(db)
    connected = enabled and wa.get_connection().get("state") == "connected"
    return {"enabled": enabled, "connected": connected}


@router.get("/settings")
def get_settings(admin: User = Depends(require_hospital_admin_or_above), db: Session = Depends(get_db)):
    return wa.get_settings(db)


@router.put("/settings")
def update_settings(
    body: SettingsUpdate,
    admin: User = Depends(require_hospital_admin_or_above),
    db: Session = Depends(get_db),
):
    try:
        wa.save_settings(
            db,
            enabled=body.enabled,
            default_country_code=body.default_country_code,
            templates=body.templates,
            user_id=admin.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if body.enabled is True:
        wa.ensure_sidecar_running()
    elif body.enabled is False:
        wa.stop_sidecar()
    log_action(db, admin, "update_whatsapp_settings", "settings", "whatsapp", None,
               "WhatsApp settings updated", details={"enabled": body.enabled})
    return wa.get_settings(db)


@router.get("/connection")
def connection(admin: User = Depends(require_hospital_admin_or_above), db: Session = Depends(get_db)):
    """Connection state + QR (data URL) for linking the hospital's WhatsApp."""
    if not wa.is_enabled(db):
        return {"state": "disabled"}
    ok, msg = wa.ensure_sidecar_running()
    conn = wa.get_connection()
    if conn.get("state") == "stopped":
        conn["state"] = "starting" if ok else "unavailable"
        conn["message"] = msg
    return conn


@router.post("/logout")
def logout(admin: User = Depends(require_hospital_admin_or_above), db: Session = Depends(get_db)):
    try:
        wa.logout()
    except wa.WhatsAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    log_action(db, admin, "whatsapp_unlink", "settings", "whatsapp", None, "WhatsApp unlinked")
    return {"ok": True}


@router.post("/send")
async def send_message(
    phone: str = Form(...),
    kind: str = Form("custom"),
    message: Optional[str] = Form(None),
    patient_name: str = Form(""),
    patient_id: Optional[str] = Form(None),
    context: Optional[str] = Form(None),  # JSON object of template placeholders
    files: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not wa.is_enabled(db):
        raise HTTPException(status_code=403, detail="WhatsApp messaging is disabled by the administrator")
    if kind not in wa.TEMPLATE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown message kind")
    try:
        number = wa.normalize_phone(phone, wa.get_country_code(db))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    ctx = {}
    if context:
        import json
        try:
            parsed = json.loads(context)
            ctx = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            raise HTTPException(status_code=422, detail="context must be JSON")
    if message and message.strip():
        text = message.strip()  # staff-edited text wins over the template
    else:
        hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
        ctx["message"] = ctx.get("message", "")
        text = wa.render_message(
            db, kind, patient_name=patient_name,
            hospital_name=hospital.name if hospital else "", context=ctx,
        )
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"At most {MAX_FILES} attachments per message")
    if not text and not files:
        raise HTTPException(status_code=422, detail="Nothing to send")

    attachments = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"{f.filename or 'Attachment'} is too large (15 MB max)")
        mimetype = f.content_type or "application/pdf"
        if mimetype not in ALLOWED_MIME:
            raise HTTPException(status_code=415, detail="Only PDF, PNG or JPEG attachments are allowed")
        if mimetype == "application/pdf" and not data.startswith(b"%PDF"):
            raise HTTPException(status_code=422, detail=f"{f.filename or 'Attachment'} is not a valid PDF")
        attachments.append((data, f.filename or "document.pdf", mimetype))

    # First attachment carries the text as its caption; the rest follow without one.
    sent = 0
    try:
        if not attachments:
            wa.send(number, text)
        for idx, (data, filename, mimetype) in enumerate(attachments):
            wa.send(number, text if idx == 0 else "", data, filename, mimetype)
            sent += 1
    except wa.WhatsAppError as exc:
        log_action(db, current_user, "whatsapp_send_failed", "whatsapp", kind, patient_id,
                   f"WhatsApp {kind} failed after {sent}/{len(attachments)} attachments: {exc}")
        detail = str(exc)
        if sent:
            detail = f"{detail} ({sent} of {len(attachments)} attachments were already delivered)"
        raise HTTPException(status_code=502, detail=detail)
    names = ", ".join(a[1] for a in attachments)
    log_action(db, current_user, "whatsapp_send", "whatsapp", kind, patient_id,
               f"WhatsApp {kind} sent to ***{number[-4:]}" + (f" with {names}" if names else ""))
    return {"ok": True, "attachments": len(attachments)}


@router.get("/templates/preview")
def preview(kind: str, patient_name: str = "Patient", current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Render the saved template so the UI can prefill an editable message."""
    if kind not in wa.TEMPLATE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown message kind")
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    return {"message": wa.render_message(db, kind, patient_name=patient_name,
                                         hospital_name=hospital.name if hospital else "")}
