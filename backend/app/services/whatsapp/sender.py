"""Send one prepared PDF. Modules call this, or the document registry calls it."""

import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.whatsapp import WhatsAppMessage
from app.services.audit_service import log_action
from app.services.whatsapp.media import publish
from app.services.whatsapp.msg91 import Msg91Error, send_document_template
from app.services.whatsapp.phone import InvalidPhone, normalize_phone
from app.services.whatsapp.registry import PreparedDocument
from app.services.whatsapp.settings import WhatsAppNotReady, require_ready
from app.utils.time import system_now

MAX_PDF_BYTES = 10 * 1024 * 1024
_send_lock = threading.Lock()
_recent_sends: dict[tuple, float] = {}
_DEBOUNCE_SECONDS = 5


class SendInProgress(Exception):
    pass


def _blank(value: str, fallback: str) -> str:
    text = (value or "").strip()
    return text or fallback


def _safe_filename(name: str, reference: str) -> str:
    raw = (name or "").replace("\\", "/").split("/")[-1].strip() or f"{reference or 'document'}.pdf"
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned[:120] or "document.pdf"


def _format_date(value) -> str:
    if value is None or value == "":
        return system_now().strftime("%d %b %Y")
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%d %b %Y")
        except ValueError:
            return text[:10]
    return text[:40]


def _hospital_name(db: Session, user) -> str:
    hospital = None
    hospital_id = getattr(user, "hospital_id", None)
    if hospital_id:
        hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if hospital is None:
        hospital = db.query(Hospital).first()
    return (hospital.name if hospital and hospital.name else "Hospital").strip()


def _claim_send(user_id, kind: str, resource_id: str) -> None:
    key = (user_id, kind, resource_id)
    now = time.time()
    with _send_lock:
        previous = _recent_sends.get(key)
        if previous and now - previous < _DEBOUNCE_SECONDS:
            raise SendInProgress()
        _recent_sends[key] = now
        stale = [item for item, stamp in _recent_sends.items() if now - stamp > 60]
        for item in stale:
            _recent_sends.pop(item, None)


def send_prepared_document(
    db: Session,
    user,
    *,
    kind: str,
    document: PreparedDocument,
    phone: str | None = None,
) -> WhatsAppMessage:
    """Publish the PDF and send the utility template for its family.

    Other modules can call this after they have already authorized the user
    and built ``document``. The HTTP route uses the document registry instead.
    """
    _claim_send(getattr(user, "id", None), kind, document.resource_id)
    config = require_ready(db, document.template_family)
    try:
        destination = normalize_phone(phone or document.phone or "")
    except InvalidPhone as exc:
        raise WhatsAppNotReady(str(exc)) from exc

    pdf_bytes = document.pdf_bytes or b""
    if not pdf_bytes:
        raise WhatsAppNotReady("This document did not produce a PDF.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise WhatsAppNotReady("This PDF is larger than 10 MB and cannot be sent on WhatsApp.")

    filename = _safe_filename(document.filename, document.reference)
    token = publish(pdf_bytes)
    media_url = f"{config['public_base_url']}/api/whatsapp/media/{token}"
    patient_name = _blank(document.patient_name, "Patient")
    reference = _blank(document.reference, filename[:-4])
    hospital_name = _hospital_name(db, user)
    document_date = _format_date(document.document_date)

    message = WhatsAppMessage(
        hospital_id=getattr(user, "hospital_id", None),
        kind=kind,
        template_family=document.template_family,
        resource_type=document.resource_type,
        resource_id=str(document.resource_id)[:200],
        phone=destination,
        filename=filename,
        status="failed",
        sent_by_id=getattr(user, "id", None),
        created_at=system_now(),
    )
    try:
        result = send_document_template(
            auth_key=config["auth_key"],
            integrated_number=config["integrated_number"],
            template_name=config["template_name"],
            phone=destination,
            media_url=media_url,
            filename=filename,
            body_values=[patient_name, reference, hospital_name, document_date],
        )
    except Msg91Error as exc:
        message.error = exc.detail[:500]
        db.add(message)
        db.commit()
        log_action(
            db, user, "send_whatsapp", "communications", document.resource_type,
            document.resource_id,
            f"WhatsApp send failed for {document.resource_type} {reference}",
            details={"kind": kind, "phone": destination, "error": exc.detail[:300]},
        )
        raise WhatsAppNotReady(exc.detail) from exc

    message.status = "submitted"
    message.provider_request_id = result.get("request_id") or None
    db.add(message)
    db.commit()
    db.refresh(message)
    log_action(
        db, user, "send_whatsapp", "communications", document.resource_type,
        document.resource_id,
        f"Sent {document.resource_type} {reference} on WhatsApp to {destination}",
        details={
            "kind": kind,
            "phone": destination,
            "provider": "msg91",
            "message_id": message.provider_request_id,
        },
    )
    return message
