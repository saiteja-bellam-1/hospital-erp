"""
Backup health aggregator.

`compute_backup_health()` is consumed by:
  - `GET /api/backup/health` — used by the dashboard banner to surface stale
    or broken backups on every admin page.
  - `BackupManagement` — to render a top-of-page summary card.

Status logic:
  - "broken"   : at least one configured location has `last_error` set AND
                 no successful write newer than the last error.
  - "stale"    : no successful backup to any location in the last STALE_HOURS,
                 OR no backup locations configured at all.
  - "healthy"  : at least one location wrote successfully within STALE_HOURS
                 AND no location is currently in a broken state.
  - "disabled" : no backup locations configured and the operator has
                 explicitly acknowledged the risk (config flag).

The "disabled" branch exists so a brand-new install isn't immediately red —
operators are nudged via the setup wizard's backup step, not by an emergency
banner before they've configured anything.
"""
from __future__ import annotations
import datetime
import os
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

    if not locations:
        status = "stale" if not config.get("backup_disabled_acknowledged") else "disabled"
        message = "No backup locations configured. Configure backups before relying on this install."
    elif broken:
        status = "broken"
        message = f"{len(broken)} backup location(s) failing: " + ", ".join(b["location"] for b in broken)
    elif healthy_count == 0:
        status = "stale"
        message = f"No successful backup in the last {STALE_HOURS} hours."
    else:
        status = "healthy"
        message = f"{healthy_count}/{len(locations)} location(s) backing up successfully."

    mirror = get_mirror_status()
    snapshot = get_snapshot_status()
    gdrive = get_gdrive_status()

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
        "gdrive_last_sent": gdrive.get("last_sent"),
    }


def _parse_iso(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", ""))
    except Exception:
        return None
