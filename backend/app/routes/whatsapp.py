"""WhatsApp (via Web sidecar) — admin controls and staff-triggered sends."""
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from sqlalchemy import func

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.user import User
from app.models.whatsapp import WhatsAppMessageLog
from app.services import whatsapp_service as wa
from app.services.audit_service import log_action
from app.utils.dependencies import get_current_user, require_hospital_admin_or_above
from config.database import get_db

router = APIRouter()

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES = 5
ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg"}


def _record(db: Session, user: User, kind: str, status: str, attachments: int,
            delivered: int, patient_ref: Optional[str], number: str, error: Optional[str] = None,
            sent_via: Optional[str] = None) -> None:
    """Persist one usage row. Never lets a logging problem break the send."""
    try:
        db.add(WhatsAppMessageLog(
            kind=kind, status=status, attachments=attachments, delivered=delivered,
            user_id=user.id, patient_ref=(patient_ref or None), phone_last4=number[-4:],
            error=(error or None), sent_via=(sent_via or None),
        ))
        db.commit()
    except Exception:
        db.rollback()


class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    default_country_code: Optional[str] = None
    templates: Optional[dict] = None


@router.get("/status")
def status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lightweight flag for the UI: show WhatsApp buttons only when enabled + linked."""
    enabled = wa.is_enabled(db)
    # Sending works while any linked number (primary or backup) is connected.
    slots = wa.connected_slots() if enabled else []
    return {"enabled": enabled, "connected": bool(slots), "connected_slots": slots}


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
    """Connection state + QR (data URL) for every linked-number slot.

    Top-level fields describe the primary; ``sessions`` has one entry per
    slot (primary, secondary) and ``slots`` gives the failover order.
    """
    if not wa.is_enabled(db):
        return {"state": "disabled", "slots": list(wa.SLOTS), "sessions": {}}
    ok, msg = wa.ensure_sidecar_running()
    conn = wa.get_connection()
    if conn.get("state") == "stopped":
        conn["state"] = "starting" if ok else "unavailable"
        conn["message"] = msg
        for sess in conn["sessions"].values():
            sess["state"] = conn["state"]
    conn["slots"] = list(wa.SLOTS)
    return conn


def _slot_or_422(slot: str) -> str:
    if slot not in wa.SLOTS:
        raise HTTPException(status_code=422, detail="Unknown WhatsApp slot")
    return slot


@router.post("/connection/{slot}/start")
def start_linking(slot: str, admin: User = Depends(require_hospital_admin_or_above),
                  db: Session = Depends(get_db)):
    """Show a QR for a backup number (the primary always runs)."""
    _slot_or_422(slot)
    if not wa.is_enabled(db):
        raise HTTPException(status_code=403, detail="Enable WhatsApp first")
    wa.ensure_sidecar_running()
    try:
        return wa.start_slot(slot)
    except wa.WhatsAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/logout")
def logout(slot: str = wa.PRIMARY, admin: User = Depends(require_hospital_admin_or_above),
           db: Session = Depends(get_db)):
    _slot_or_422(slot)
    try:
        wa.logout(slot)
    except wa.WhatsAppError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    label = wa.SLOT_LABELS.get(slot, slot)
    log_action(db, admin, "whatsapp_unlink", "settings", "whatsapp", None, f"WhatsApp {label} number unlinked")
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
    # Each part goes out through the primary number, failing over to the
    # secondary; once a number works the remaining parts stick to it.
    sent = 0
    used: Optional[str] = None
    used_slots: list = []
    try:
        if not attachments:
            used = wa.send_with_failover(number, text)
            used_slots.append(used)
        for idx, (data, filename, mimetype) in enumerate(attachments):
            used = wa.send_with_failover(number, text if idx == 0 else "", data, filename, mimetype, prefer=used)
            used_slots.append(used)
            sent += 1
    except wa.WhatsAppError as exc:
        _record(db, current_user, kind, "failed", len(attachments), sent, patient_id, number, str(exc),
                sent_via=",".join(dict.fromkeys(used_slots)) or None)
        log_action(db, current_user, "whatsapp_send_failed", "whatsapp", kind, patient_id,
                   f"WhatsApp {kind} failed after {sent}/{len(attachments)} attachments: {exc}")
        detail = str(exc)
        if sent:
            detail = f"{detail} ({sent} of {len(attachments)} attachments were already delivered)"
        raise HTTPException(status_code=502, detail=detail)
    via = ",".join(dict.fromkeys(used_slots))
    _record(db, current_user, kind, "sent", len(attachments), max(1, len(attachments)), patient_id, number,
            sent_via=via)
    names = ", ".join(a[1] for a in attachments)
    failover_note = "" if via == wa.PRIMARY else f" via {via} number"
    log_action(db, current_user, "whatsapp_send", "whatsapp", kind, patient_id,
               f"WhatsApp {kind} sent to ***{number[-4:]}" + (f" with {names}" if names else "") + failover_note)
    return {"ok": True, "attachments": len(attachments), "sent_via": via, "failover": via != wa.PRIMARY}


@router.get("/templates/preview")
def preview(kind: str, patient_name: str = "Patient", current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """Render the saved template so the UI can prefill an editable message."""
    if kind not in wa.TEMPLATE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown message kind")
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    return {"message": wa.render_message(db, kind, patient_name=patient_name,
                                         hospital_name=hospital.name if hospital else "")}


def _count(db: Session, start: Optional[datetime], end: Optional[datetime]) -> dict:
    q = db.query(
        WhatsAppMessageLog.kind, WhatsAppMessageLog.status,
        func.count(WhatsAppMessageLog.id), func.coalesce(func.sum(WhatsAppMessageLog.delivered), 0),
    )
    if start:
        q = q.filter(WhatsAppMessageLog.created_at >= start)
    if end:
        q = q.filter(WhatsAppMessageLog.created_at < end)
    by_kind = {k: {"kind": k, "sent": 0, "failed": 0, "whatsapp_messages": 0} for k in wa.TEMPLATE_KINDS}
    for kind, status, n, delivered in q.group_by(WhatsAppMessageLog.kind, WhatsAppMessageLog.status).all():
        row = by_kind.setdefault(kind, {"kind": kind, "sent": 0, "failed": 0, "whatsapp_messages": 0})
        row["sent" if status == "sent" else "failed"] += int(n)
        row["whatsapp_messages"] += int(delivered or 0)
    rows = list(by_kind.values())
    # Successful sends per linked number (shows how often the backup was used).
    vq = db.query(WhatsAppMessageLog.sent_via, func.count(WhatsAppMessageLog.id)).filter(
        WhatsAppMessageLog.status == "sent")
    if start:
        vq = vq.filter(WhatsAppMessageLog.created_at >= start)
    if end:
        vq = vq.filter(WhatsAppMessageLog.created_at < end)
    by_number = {slot: 0 for slot in wa.SLOTS}
    for via, n in vq.group_by(WhatsAppMessageLog.sent_via).all():
        for slot in (via or wa.PRIMARY).split(","):  # rows before failover existed = primary
            by_number[slot] = by_number.get(slot, 0) + int(n)
    return {
        "by_kind": rows,
        "by_number": by_number,
        "sent": sum(r["sent"] for r in rows),
        "failed": sum(r["failed"] for r in rows),
        "whatsapp_messages": sum(r["whatsapp_messages"] for r in rows),
    }


@router.get("/stats")
def stats(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    admin: User = Depends(require_hospital_admin_or_above),
    db: Session = Depends(get_db),
):
    """Usage counts per topic for a date range (inclusive), plus today / month / all-time totals.

    `sent` = successful send actions (one per Send press); `whatsapp_messages` also counts each
    extra attachment, since WhatsApp delivers every attached file as its own message.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    start = datetime.combine(date_from, time.min) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), time.min) if date_to else None
    today = date.today()
    today_start = datetime.combine(today, time.min)
    month_start = datetime.combine(today.replace(day=1), time.min)
    tomorrow = today_start + timedelta(days=1)

    def brief(c: dict) -> dict:
        return {k: c[k] for k in ("sent", "failed", "whatsapp_messages")}

    return {
        "range": {"date_from": date_from, "date_to": date_to},
        **_count(db, start, end),
        "summary": {
            "today": brief(_count(db, today_start, tomorrow)),
            "this_month": brief(_count(db, month_start, tomorrow)),
            "all_time": brief(_count(db, None, None)),
        },
    }
