"""
Backup health aggregator.

`compute_backup_health()` is consumed by:
  - `GET /api/backup/health` — used by the dashboard banner to surface stale
    or broken backups on every admin page.
  - `BackupManagement` — to render a top-of-page summary card.

Status logic:
  - "broken"   : at least one configured location has `last_error` set AND
                 no successful write newer than the last error, OR Google Drive
                 is enabled and its last attempt failed.
  - "stale"    : no successful backup to any location in the last STALE_HOURS,
                 OR no backup locations configured at all, OR Drive has not
                 uploaded in more than a day.
  - "healthy"  : at least one location wrote successfully within STALE_HOURS
                 AND no location (including Drive) is currently broken/stale.
  - "disabled" : no backup locations configured and the operator has
                 explicitly acknowledged the risk (config flag).

The "disabled" branch exists so a brand-new install isn't immediately red —
operators are nudged via the setup wizard's backup step, not by an emergency
banner before they've configured anything.
"""
from __future__ import annotations
import datetime
from typing import Optional


STALE_HOURS = 6


def compute_backup_health() -> dict:
    """Build a compact health report; meant to be cheap to call frequently."""
    from app.utils.config import (
        load_config,
        get_per_location_status,
        get_snapshot_status,
        get_mirror_status,
        get_gdrive_status,
    )

    config = load_config()
    locations = config.get("backup_locations", []) or []
    per_location = get_per_location_status() if locations else {}

    now = datetime.datetime.now()
    broken: list[dict] = []
    stale: list[dict] = []
    healthy_count = 0
    most_recent_success: Optional[str] = None

    for loc, snap in per_location.items():
        last_success = snap.get("last_success")
        last_error = snap.get("last_error")
        writable = snap.get("writable", True)

        success_dt = _parse_iso(last_success)
        if last_error and (success_dt is None or _parse_iso(snap.get("last_attempt")) and (success_dt or datetime.datetime.min) < (_parse_iso(snap.get("last_attempt")) or now)):
            # last_error is set and we don't have a more recent success → broken
            broken.append({
                "location": loc,
                "last_success": last_success,
                "last_error": last_error,
                "writable": writable,
            })
            continue

        if success_dt and (now - success_dt) <= datetime.timedelta(hours=STALE_HOURS):
            healthy_count += 1
            if most_recent_success is None or success_dt > (_parse_iso(most_recent_success) or datetime.datetime.min):
                most_recent_success = last_success
        else:
            stale.append({
                "location": loc,
                "last_success": last_success,
                "writable": writable,
            })

    mirror = get_mirror_status()
    snapshot = get_snapshot_status()
    gdrive = get_gdrive_status()
    gdrive_state = classify_gdrive(gdrive, now)

    if gdrive_state["status"] == "error":
        broken.append({
            "location": "Google Drive",
            "last_success": gdrive.get("last_sent"),
            "last_error": gdrive.get("last_error") or gdrive_state["detail"],
            "writable": False,
        })
    elif gdrive_state["status"] == "stale":
        stale.append({
            "location": "Google Drive",
            "last_success": gdrive.get("last_sent"),
            "writable": True,
        })

    if not locations:
        status = "stale" if not config.get("backup_disabled_acknowledged") else "disabled"
        message = "No backup locations configured. Configure backups before relying on this install."
        if gdrive_state["status"] == "error":
            status = "broken"
            message = "Google Drive backup is failing. " + (gdrive.get("last_error") or "")
        elif gdrive_state["status"] == "healthy":
            message = "No local backup locations configured. Google Drive backup is healthy."
    elif broken:
        status = "broken"
        message = f"{len(broken)} backup location(s) failing: " + ", ".join(b["location"] for b in broken)
    elif healthy_count == 0 or gdrive_state["status"] == "stale":
        status = "stale"
        if gdrive_state["status"] == "stale":
            message = gdrive_state.get("detail") or "Google Drive backup is stale."
        else:
            message = f"No successful backup in the last {STALE_HOURS} hours."
    else:
        status = "healthy"
        n = healthy_count + (1 if gdrive_state["status"] == "healthy" else 0)
        denom = len(locations) + (1 if gdrive.get("enabled") else 0)
        message = f"{n}/{denom} location(s) backing up successfully."

    return {
        "status": status,
        "message": message,
        "stale_hours_threshold": STALE_HOURS,
        "locations_configured": len(locations),
        "locations_healthy": healthy_count,
        "broken": broken,
        "stale": stale,
        "most_recent_success": most_recent_success,
        "mirror_running": mirror.get("running"),
        "snapshot_running": snapshot.get("running"),
        "gdrive_enabled": gdrive.get("enabled"),
        "gdrive_running": gdrive.get("running"),
        "gdrive_last_sent": gdrive.get("last_sent"),
        "gdrive_last_error": gdrive.get("last_error"),
        "gdrive_status": gdrive_state["status"],
        "gdrive_message": gdrive_state.get("detail"),
    }


def classify_gdrive(gdrive: dict, now: datetime.datetime) -> dict:
    """Map Drive status into the same healthy/error/stale/disabled vocabulary.

    Daily uploads: sent today → healthy; sent yesterday → waiting (the 10-min
    checker may not have run yet today); older than that → stale.
    """
    if not gdrive.get("enabled"):
        return {"status": "disabled", "detail": None}
    last_error = gdrive.get("last_error")
    if last_error:
        return {"status": "error", "detail": last_error}
    last_sent = gdrive.get("last_sent")
    if not last_sent:
        return {"status": "waiting", "detail": "No Google Drive backup has been sent yet."}
    sent_date = _parse_date(last_sent)
    if sent_date is None:
        return {"status": "waiting", "detail": None}
    age_days = (now.date() - sent_date).days
    if age_days <= 0:
        return {"status": "healthy", "detail": f"Last sent {last_sent}"}
    if age_days == 1:
        return {"status": "waiting", "detail": f"Last sent {last_sent}"}
    return {"status": "stale", "detail": f"Last Google Drive backup was {age_days} days ago ({last_sent})."}


def _parse_date(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _parse_iso(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None
