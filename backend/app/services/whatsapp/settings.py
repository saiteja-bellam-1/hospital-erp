"""MSG91 settings stored on the hospital, not in source control."""

from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings
from app.utils.time import system_now

CATEGORY = "whatsapp"

TEMPLATE_FAMILIES = ("invoice", "lab_report", "prescription", "discharge")

SETTING_KEYS = (
    "enabled",
    "auth_key",
    "integrated_number",
    "public_base_url",
    "template_invoice",
    "template_lab_report",
    "template_prescription",
    "template_discharge",
)

_TEMPLATE_KEY = {
    "invoice": "template_invoice",
    "lab_report": "template_lab_report",
    "prescription": "template_prescription",
    "discharge": "template_discharge",
}


class WhatsAppNotReady(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _row(db: Session, key: str):
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == CATEGORY,
            HospitalSettings.setting_key == key,
        )
        .first()
    )


def _value(db: Session, key: str, default: str = "") -> str:
    row = _row(db, key)
    if not row or row.setting_value is None:
        return default
    return row.setting_value


def _write(db: Session, key: str, value: str, user_id: int | None, setting_type: str = "string"):
    row = _row(db, key)
    if row:
        row.setting_value = value
        row.setting_type = setting_type
        row.updated_at = system_now()
        return
    db.add(HospitalSettings(
        setting_category=CATEGORY,
        setting_key=key,
        setting_value=value,
        setting_type=setting_type,
        description=f"WhatsApp {key}",
        created_by=user_id,
    ))


def is_enabled(db: Session) -> bool:
    raw = _value(db, "enabled", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def public_settings(db: Session) -> dict:
    auth = _value(db, "auth_key").strip()
    return {
        "enabled": is_enabled(db),
        "auth_key_set": bool(auth),
        "integrated_number": _value(db, "integrated_number").strip(),
        "public_base_url": _value(db, "public_base_url").strip(),
        "template_invoice": _value(db, "template_invoice").strip(),
        "template_lab_report": _value(db, "template_lab_report").strip(),
        "template_prescription": _value(db, "template_prescription").strip(),
        "template_discharge": _value(db, "template_discharge").strip(),
    }


def update_settings(db: Session, payload: dict, user_id: int | None) -> dict:
    if "enabled" in payload and payload["enabled"] is not None:
        _write(db, "enabled", "true" if payload["enabled"] else "false", user_id, "boolean")
    auth_key = payload.get("auth_key")
    if isinstance(auth_key, str) and auth_key.strip():
        _write(db, "auth_key", auth_key.strip(), user_id)
    for key in (
        "integrated_number",
        "public_base_url",
        "template_invoice",
        "template_lab_report",
        "template_prescription",
        "template_discharge",
    ):
        if key not in payload or payload[key] is None:
            continue
        value = str(payload[key]).strip()
        if key == "public_base_url" and value:
            value = validate_public_base_url(value)
        if key == "integrated_number" and value:
            from app.services.whatsapp.phone import InvalidPhone, normalize_phone
            try:
                value = normalize_phone(value)
            except InvalidPhone as exc:
                raise WhatsAppNotReady(str(exc)) from exc
        _write(db, key, value, user_id)
    db.commit()
    return public_settings(db)


def validate_public_base_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise WhatsAppNotReady("Public base URL must be an http or https address.")
    if parsed.query or parsed.fragment or (parsed.path not in ("", "/")):
        raise WhatsAppNotReady("Public base URL must be the hospital origin only, without a path.")
    return f"{parsed.scheme}://{parsed.netloc}"


def require_ready(db: Session, template_family: str) -> dict:
    """Return the secrets needed to send. Raises WhatsAppNotReady when incomplete."""
    from app.services.license_service import license_allows_whatsapp

    if not license_allows_whatsapp(db):
        raise WhatsAppNotReady("WhatsApp is not included in this hospital's license.", 403)
    if not is_enabled(db):
        raise WhatsAppNotReady("WhatsApp sending is turned off for this hospital.", 403)
    if template_family not in _TEMPLATE_KEY:
        raise WhatsAppNotReady(f"Unknown WhatsApp template family '{template_family}'.")

    auth_key = _value(db, "auth_key").strip()
    integrated_number = _value(db, "integrated_number").strip()
    public_base_url = _value(db, "public_base_url").strip()
    template_name = _value(db, _TEMPLATE_KEY[template_family]).strip()
    missing = []
    if not auth_key:
        missing.append("MSG91 auth key")
    if not integrated_number:
        missing.append("WhatsApp number")
    if not public_base_url:
        missing.append("public base URL")
    if not template_name:
        missing.append(f"{template_family.replace('_', ' ')} template name")
    if missing:
        raise WhatsAppNotReady("WhatsApp settings are incomplete: " + ", ".join(missing) + ".")
    return {
        "auth_key": auth_key,
        "integrated_number": integrated_number,
        "public_base_url": validate_public_base_url(public_base_url),
        "template_name": template_name,
    }
