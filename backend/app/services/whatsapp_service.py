"""WhatsApp Web integration.

The ERP never talks to WhatsApp directly. A small Node sidecar
(``whatsapp-sidecar/``, built on Baileys) keeps one linked-device session
(QR scan once) and exposes a localhost-only HTTP API. This module:

* stores the admin on/off switch + message templates in ``hospital_settings``
* talks to the sidecar (status / QR / send / logout)
* starts the sidecar process on demand when WhatsApp is enabled
* normalises phone numbers and renders message templates

Unofficial WhatsApp Web automation can get a number banned; the feature is
therefore opt-in (off by default) and meant for staff-triggered 1:1 messages.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings
from app.utils.paths import get_base_dir, get_bundle_dir, get_state_dir, is_bundled

logger = logging.getLogger(__name__)

CATEGORY = "whatsapp"
KEY_ENABLED = "enabled"
KEY_COUNTRY_CODE = "default_country_code"
KEY_TEMPLATES = "templates"

SIDECAR_HOST = "127.0.0.1"
SIDECAR_PORT = int(os.environ.get("WHATSAPP_SIDECAR_PORT", "9100"))
SIDECAR_URL = f"http://{SIDECAR_HOST}:{SIDECAR_PORT}"
SEND_TIMEOUT_S = 60

# kind -> default template. Placeholders: {patient_name} {hospital_name}
# plus whatever the caller passes in ``context`` (doctor_name, date, ...).
DEFAULT_TEMPLATES: dict[str, str] = {
    "consultation_confirmation": (
        "Dear {patient_name}, your consultation at {hospital_name} is confirmed"
        "{when_clause}{doctor_clause}. Please carry this message and arrive 10 minutes early."
    ),
    "lab_order_confirmation": (
        "Dear {patient_name}, your lab order{order_clause} at {hospital_name} is confirmed."
        " We will share the reports on WhatsApp once they are ready."
    ),
    "lab_report": (
        "Dear {patient_name}, your lab report from {hospital_name} is attached."
    ),
    "prescription": (
        "Dear {patient_name}, your prescription from {hospital_name} is attached."
        " Please follow the doctor's advice."
    ),
    "consultation_invoice": (
        "Dear {patient_name}, thank you for visiting {hospital_name}."
        " Your consultation invoice is attached."
    ),
    "lab_invoice": (
        "Dear {patient_name}, thank you for choosing {hospital_name}."
        " Your lab invoice is attached."
    ),
    "pharmacy_invoice": (
        "Dear {patient_name}, thank you for purchasing from {hospital_name} pharmacy."
        " Your invoice is attached."
    ),
    "custom": "{message}",
}
TEMPLATE_KINDS = tuple(DEFAULT_TEMPLATES)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def _row(db: Session, key: str) -> Optional[HospitalSettings]:
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == CATEGORY,
            HospitalSettings.setting_key == key,
        )
        .first()
    )


def _set(db: Session, key: str, value: str, setting_type: str, user_id: Optional[int]) -> None:
    row = _row(db, key)
    if row:
        row.setting_value = value
        row.setting_type = setting_type
    else:
        db.add(
            HospitalSettings(
                setting_category=CATEGORY,
                setting_key=key,
                setting_value=value,
                setting_type=setting_type,
                description=f"WhatsApp: {key}",
                created_by=user_id,
            )
        )


def is_enabled(db: Session) -> bool:
    row = _row(db, KEY_ENABLED)
    return bool(row and str(row.setting_value).strip().lower() in ("1", "true", "yes", "on"))


def get_country_code(db: Session) -> str:
    row = _row(db, KEY_COUNTRY_CODE)
    code = re.sub(r"\D", "", (row.setting_value if row else "") or "")
    return code or "91"


def get_templates(db: Session) -> dict[str, str]:
    merged = dict(DEFAULT_TEMPLATES)
    row = _row(db, KEY_TEMPLATES)
    if row and row.setting_value:
        try:
            saved = json.loads(row.setting_value)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if k in merged and isinstance(v, str) and v.strip():
                        merged[k] = v
        except ValueError:
            pass
    return merged


def get_settings(db: Session) -> dict[str, Any]:
    return {
        "enabled": is_enabled(db),
        "default_country_code": get_country_code(db),
        "templates": get_templates(db),
        "default_templates": DEFAULT_TEMPLATES,
    }


def save_settings(
    db: Session,
    *,
    enabled: Optional[bool] = None,
    default_country_code: Optional[str] = None,
    templates: Optional[dict[str, str]] = None,
    user_id: Optional[int] = None,
) -> None:
    if enabled is not None:
        _set(db, KEY_ENABLED, "true" if enabled else "false", "boolean", user_id)
    if default_country_code is not None:
        code = re.sub(r"\D", "", default_country_code)
        if not code or len(code) > 4:
            raise ValueError("Country code must be 1-4 digits")
        _set(db, KEY_COUNTRY_CODE, code, "string", user_id)
    if templates is not None:
        clean = {
            k: v for k, v in templates.items()
            if k in DEFAULT_TEMPLATES and isinstance(v, str) and v.strip()
        }
        _set(db, KEY_TEMPLATES, json.dumps(clean), "json", user_id)
    db.commit()


# --------------------------------------------------------------------------- #
# Phone + message helpers
# --------------------------------------------------------------------------- #
def normalize_phone(raw: str, default_country_code: str = "91") -> str:
    """Return digits-only E.164 without '+', or raise ValueError."""
    s = (raw or "").strip()
    has_plus = s.startswith("+") or s.startswith("00")
    digits = re.sub(r"\D", "", s)
    if s.startswith("00"):
        digits = digits[2:]
    if not digits:
        raise ValueError("Phone number is required")
    if not has_plus:
        digits = digits.lstrip("0") if len(digits) > 10 else digits
        if len(digits) == 10:
            digits = default_country_code + digits
    if not 8 <= len(digits) <= 15:
        raise ValueError("Phone number looks invalid")
    return digits


class _SafeDict(dict):
    def __missing__(self, key):  # unknown placeholders render as empty
        return ""


def render_message(
    db: Session,
    kind: str,
    *,
    patient_name: str = "",
    hospital_name: str = "",
    context: Optional[dict[str, Any]] = None,
) -> str:
    templates = get_templates(db)
    tpl = templates.get(kind) or templates["custom"]
    ctx: dict[str, Any] = {k: ("" if v is None else str(v)) for k, v in (context or {}).items()}
    ctx["patient_name"] = patient_name or "Patient"
    ctx["hospital_name"] = hospital_name or "our hospital"
    when = " ".join(x for x in (ctx.get("date", ""), ctx.get("time", "")) if x)
    ctx["when_clause"] = f" for {when}" if when else ""
    ctx["doctor_clause"] = f" with {ctx['doctor_name']}" if ctx.get("doctor_name") else ""
    ctx["order_clause"] = f" ({ctx['order_number']})" if ctx.get("order_number") else ""
    return tpl.format_map(_SafeDict(ctx)).strip()


# --------------------------------------------------------------------------- #
# Sidecar process management
# --------------------------------------------------------------------------- #
_proc_lock = threading.Lock()
_proc: Optional[subprocess.Popen] = None


def _token_path() -> str:
    return os.path.join(get_state_dir(), "whatsapp", ".sidecar_token")


def _get_token() -> str:
    path = _token_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            tok = fh.read().strip()
            if tok:
                return tok
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tok = secrets.token_urlsafe(32)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(tok)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return tok


def _sidecar_dir() -> str:
    for base in (get_bundle_dir(), get_base_dir(), os.path.dirname(get_base_dir())):
        cand = os.path.join(base, "whatsapp-sidecar")
        if os.path.isfile(os.path.join(cand, "index.js")):
            return cand
    return os.path.join(os.path.dirname(get_base_dir()), "whatsapp-sidecar")


def _find_node() -> Optional[str]:
    if is_bundled():
        bundled = os.path.join(get_base_dir(), "node", "node.exe")
        if os.path.isfile(bundled):
            return bundled
    return os.environ.get("WHATSAPP_NODE_BIN") or shutil.which("node")


def ensure_sidecar_running() -> tuple[bool, str]:
    """Start the sidecar if it isn't answering. Returns (ok, message)."""
    global _proc
    if _ping():
        return True, "running"
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            return True, "starting"
        node = _find_node()
        if not node:
            return False, "Node.js was not found. Install Node 18+ or set WHATSAPP_NODE_BIN."
        sdir = _sidecar_dir()
        if not os.path.isfile(os.path.join(sdir, "index.js")):
            return False, f"WhatsApp sidecar not found at {sdir}"
        if not os.path.isdir(os.path.join(sdir, "node_modules")):
            return False, f"Run 'npm install' in {sdir} first."
        auth_dir = os.path.join(get_state_dir(), "whatsapp", "auth")
        os.makedirs(auth_dir, exist_ok=True)
        env = dict(os.environ)
        env.update(
            {
                "WA_PORT": str(SIDECAR_PORT),
                "WA_HOST": SIDECAR_HOST,
                "WA_TOKEN": _get_token(),
                "WA_AUTH_DIR": auth_dir,
            }
        )
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        log_path = os.path.join(get_state_dir(), "whatsapp", "sidecar.log")
        logf = open(log_path, "ab")
        try:
            _proc = subprocess.Popen(
                [node, "index.js"], cwd=sdir, env=env,
                stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, **kwargs,
            )
        except OSError as exc:
            logger.exception("Failed to start WhatsApp sidecar")
            return False, f"Could not start sidecar: {exc}"
        return True, "starting"


def stop_sidecar() -> None:
    global _proc
    with _proc_lock:
        if _proc is not None and _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _proc.kill()
        _proc = None


# --------------------------------------------------------------------------- #
# Sidecar HTTP client
# --------------------------------------------------------------------------- #
class WhatsAppError(Exception):
    pass


def _request(method: str, path: str, body: Optional[dict] = None, timeout: float = 5) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        SIDECAR_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Token": _get_token()},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        raise WhatsAppError(detail or f"WhatsApp service error ({exc.code})") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise WhatsAppError("WhatsApp service is not running") from exc


def _ping() -> bool:
    try:
        _request("GET", "/status", timeout=1.5)
        return True
    except WhatsAppError:
        return False


def get_connection() -> dict:
    """{state: stopped|starting|qr|connecting|connected, qr?: dataURL, phone?: str}"""
    try:
        return _request("GET", "/status")
    except WhatsAppError:
        return {"state": "stopped"}


def logout() -> None:
    _request("POST", "/logout", {}, timeout=15)


def send(phone: str, text: str, file_bytes: Optional[bytes] = None,
         filename: Optional[str] = None, mimetype: Optional[str] = None) -> dict:
    payload: dict[str, Any] = {"phone": phone, "text": text}
    if file_bytes:
        payload["file_base64"] = base64.b64encode(file_bytes).decode("ascii")
        payload["filename"] = filename or "document.pdf"
        payload["mimetype"] = mimetype or "application/pdf"
    return _request("POST", "/send", payload, timeout=SEND_TIMEOUT_S)
