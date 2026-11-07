"""14-day machine trial. No SQLAlchemy — dbcheck.exe imports this module.

The clock is keyed to the Windows ``MachineGuid`` and stored outside the
install folder (HKLM and ProgramData). Deleting the app and its data folder
does not start the 14 days over. A second ``trial_begin`` keeps the original
``started_at`` and ``expires_at``.

The HMAC stops casual edits of the JSON. It is not a defense against someone
who patches the executable or deletes both stores as an administrator.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Callable, Optional

TRIAL_DAYS = 14
STATUS_TRIAL = "trial"
STATUS_TRIAL_EXPIRED = "trial_expired"
STATUS_NONE = "none"

# Product modules unlocked during an active trial. Paid add-ons
# (customisation, and WhatsApp where that build has it) are intentionally
# absent — keep this list aligned with CANONICAL_SYSTEM_MODULES names.
TRIAL_FEATURES = (
    "outpatient",
    "inpatient",
    "lab",
    "pharmacy",
    "physiotherapy",
    "ehr",
    "billing",
    "admin",
)

# Stops a text editor from extending expires_at. Not secret against a patched exe.
_HMAC_KEY = b"KT HEALTH ERP trial v1\x00kthealth-trial-record"

_REG_PATH = r"SOFTWARE\KT Health ERP\Trial"
_REG_VALUE = "record"
_USERS_SID = "*S-1-5-32-545"  # BUILTIN\Users


class _Override:
    """Test seam. Production leaves every field None so the real stores are used."""

    directory: Optional[str] = None
    registry: Optional[dict] = None
    fingerprint: Optional[str] = None
    now_fn: Optional[Callable[[], datetime]] = None


_override = _Override()


def use_isolated_store(directory: str, fingerprint: str = "fp-test") -> None:
    """Point reads and writes at a temp folder and an in-memory registry.

    Tests call this so a run never creates a real trial on the developer PC.
    """
    _override.directory = directory
    _override.registry = {"hklm": "", "hkcu": ""}
    _override.fingerprint = fingerprint


def clear_isolated_store() -> None:
    _override.directory = None
    _override.registry = None
    _override.fingerprint = None
    _override.now_fn = None


def set_now(now_fn: Optional[Callable[[], datetime]]) -> None:
    _override.now_fn = now_fn


def _now() -> datetime:
    if _override.now_fn is not None:
        return _override.now_fn()
    return datetime.utcnow()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def _canonical(payload: dict) -> dict:
    return {
        "fingerprint": payload.get("fingerprint") or "",
        "started_at": payload.get("started_at") or "",
        "expires_at": payload.get("expires_at") or "",
        "last_seen_at": payload.get("last_seen_at") or "",
    }


def _sign(payload: dict) -> str:
    body = json.dumps(_canonical(payload), separators=(",", ":"), sort_keys=True)
    return hmac.new(_HMAC_KEY, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify(payload: dict) -> bool:
    got = str(payload.get("hmac") or "")
    if not got:
        return False
    expect = _sign(payload)
    return hmac.compare_digest(got, expect)


def machine_fingerprint() -> str:
    """Stable per Windows install. Empty when MachineGuid cannot be read."""
    if _override.fingerprint:
        return _override.fingerprint
    guid = _read_machine_guid()
    if not guid:
        return ""
    return hashlib.sha256(guid.strip().lower().encode("utf-8")).hexdigest()


def _read_machine_guid() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, access) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return str(value or "").strip()
    except OSError:
        return ""


def _programdata_dir() -> str:
    if _override.directory:
        return _override.directory
    base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
    return os.path.join(base, "KTHealthERP")


def _trial_path() -> str:
    return os.path.join(_programdata_dir(), "trial.json")


def _reg_access(write: bool) -> int:
    import winreg
    flag = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
    return flag | getattr(winreg, "KEY_WOW64_64KEY", 0)


def _hive(name: str):
    import winreg
    if name == "hkcu":
        return winreg.HKEY_CURRENT_USER
    return winreg.HKEY_LOCAL_MACHINE


def _read_file_raw() -> str:
    try:
        with open(_trial_path(), "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _read_reg_raw(name: str) -> str:
    if _override.registry is not None:
        return str(_override.registry.get(name) or "")
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(_hive(name), _REG_PATH, 0, _reg_access(False)) as key:
            value, _ = winreg.QueryValueEx(key, _REG_VALUE)
        return str(value or "")
    except OSError:
        return ""


def _grant_users_modify(path: str) -> None:
    """Let a standard user rewrite last_seen. Skipped for the temp test store."""
    if _override.directory or sys.platform != "win32":
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["icacls", path, "/grant", f"{_USERS_SID}:(M)"],
            capture_output=True,
            check=False,
            creationflags=flags,
        )
    except OSError:
        pass


def _write_file(record: dict) -> bool:
    path = _trial_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, separators=(",", ":"))
    except OSError:
        return False
    _grant_users_modify(path)
    _grant_users_modify(os.path.dirname(path))
    return True


def _write_reg(name: str, record: dict) -> bool:
    raw = json.dumps(record, separators=(",", ":"))
    if _override.registry is not None:
        _override.registry[name] = raw
        return True
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.CreateKeyEx(_hive(name), _REG_PATH, 0, _reg_access(True)) as key:
            winreg.SetValueEx(key, _REG_VALUE, 0, winreg.REG_SZ, raw)
        return True
    except OSError:
        return False


def _persist(record: dict) -> bool:
    """Write every store we can. Durable if the file or HKLM succeeded.

    HKCU alone is not durable: the installer runs elevated, so that hive is
    the admin's, and another Windows user would not see it.
    """
    file_ok = _write_file(record)
    hklm_ok = _write_reg("hklm", record)
    _write_reg("hkcu", record)
    return file_ok or hklm_ok


def _parse_blob(raw: str, fingerprint: str) -> tuple[str, Optional[dict]]:
    if not raw:
        return "missing", None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "tampered", None
    if not isinstance(data, dict) or not _verify(data):
        return "tampered", None
    if data.get("fingerprint") != fingerprint:
        return "foreign", None
    return "ours", data


def _merge_ours(records: list[dict]) -> Optional[dict]:
    """Keep the earliest window and the latest last_seen.

    A second copy with a later ``started_at`` must not extend the trial.
    """
    if not records:
        return None
    base = min(records, key=lambda row: row.get("started_at") or "9999")
    newest = base.get("last_seen_at") or ""
    for row in records:
        seen = row.get("last_seen_at") or ""
        if seen > newest:
            newest = seen
    merged = {
        "fingerprint": base.get("fingerprint") or "",
        "started_at": base.get("started_at") or "",
        "expires_at": base.get("expires_at") or "",
        "last_seen_at": newest or base.get("started_at") or "",
    }
    merged["hmac"] = _sign(merged)
    return merged


def _load(fingerprint: str) -> tuple[Optional[dict], bool]:
    ours: list[dict] = []
    tampered = False
    for raw in (_read_file_raw(), _read_reg_raw("hklm"), _read_reg_raw("hkcu")):
        kind, record = _parse_blob(raw, fingerprint)
        if kind == "tampered":
            tampered = True
        elif kind == "ours" and record is not None:
            ours.append(record)
    return _merge_ours(ours), tampered


def _days_remaining(expires: datetime, effective: datetime) -> int:
    seconds = (expires - effective).total_seconds()
    if seconds <= 0:
        return 0
    return math.ceil(seconds / 86400)


def evaluate(record: dict, now: Optional[datetime] = None) -> dict:
    """Status of a verified record.

    When the clock is behind ``last_seen_at``, expiry is judged against
    ``last_seen_at`` so setting the clock back does not add days.
    """
    now = now or _now()
    started = _parse(record.get("started_at") or "")
    expires = _parse(record.get("expires_at") or "")
    last_seen = _parse(record.get("last_seen_at") or "")
    effective = now
    if last_seen is not None and now < last_seen:
        effective = last_seen
    if expires is None or started is None:
        status = STATUS_TRIAL_EXPIRED
        days = 0
    elif effective < expires:
        status = STATUS_TRIAL
        days = _days_remaining(expires, effective)
    else:
        status = STATUS_TRIAL_EXPIRED
        days = 0
    return {
        "status": status,
        "days_remaining": days,
        "started_at": record.get("started_at") or None,
        "expires_at": expires.isoformat() if expires else None,
        "fingerprint": record.get("fingerprint") or "",
    }


def _touch(record: dict) -> dict:
    """Advance last_seen. Never move it backwards."""
    now = _now()
    last = _parse(record.get("last_seen_at") or "")
    if last is not None and now <= last:
        return record
    updated = {
        "fingerprint": record.get("fingerprint") or "",
        "started_at": record.get("started_at") or "",
        "expires_at": record.get("expires_at") or "",
        "last_seen_at": _iso(now),
    }
    updated["hmac"] = _sign(updated)
    return updated


def _public(info: dict, *, created: bool, ok: bool = True, error: str = "") -> dict:
    payload = {
        "ok": ok,
        "created": created,
        "status": info.get("status") or STATUS_NONE,
        "days_remaining": int(info.get("days_remaining") or 0),
        "expires_at": info.get("expires_at"),
        "started_at": info.get("started_at"),
    }
    if error:
        payload["error"] = error
    return payload


def _none_payload() -> dict:
    return _public(
        {"status": STATUS_NONE, "days_remaining": 0, "expires_at": None, "started_at": None},
        created=False,
    )


def _expired_payload() -> dict:
    return _public(
        {
            "status": STATUS_TRIAL_EXPIRED,
            "days_remaining": 0,
            "expires_at": None,
            "started_at": None,
        },
        created=False,
    )


def trial_status(*, touch: bool = True) -> dict:
    """Read the trial for this PC. Does not create a record."""
    fingerprint = machine_fingerprint()
    if not fingerprint:
        return _none_payload()
    record, tampered = _load(fingerprint)
    if record is None:
        if tampered:
            return _expired_payload()
        return _none_payload()
    if touch:
        updated = _touch(record)
        if updated is not record:
            _persist(updated)
            record = updated
    return _public(evaluate(record), created=False)


def trial_begin() -> dict:
    """Start the clock if this PC has no record. Never reset an existing one.

    Called by the installer on a fresh install that did not select a ``.lic``.
    The running app does not call this, so a source checkout cannot start a trial.
    """
    fingerprint = machine_fingerprint()
    if not fingerprint:
        return _public(
            {"status": STATUS_NONE, "days_remaining": 0, "expires_at": None, "started_at": None},
            created=False,
            ok=False,
            error="machine fingerprint unavailable",
        )
    record, tampered = _load(fingerprint)
    if record is not None:
        updated = _touch(record)
        _persist(updated)
        return _public(evaluate(updated), created=False)
    if tampered:
        # A broken signature on our own record must not mint a fresh 14 days.
        return _expired_payload()

    now = _now()
    expires = now + timedelta(days=TRIAL_DAYS)
    created = {
        "fingerprint": fingerprint,
        "started_at": _iso(now),
        "expires_at": _iso(expires),
        "last_seen_at": _iso(now),
    }
    created["hmac"] = _sign(created)
    if not _persist(created):
        return _public(
            {"status": STATUS_NONE, "days_remaining": 0, "expires_at": None, "started_at": None},
            created=False,
            ok=False,
            error="could not store trial record",
        )
    return _public(evaluate(created), created=True)
