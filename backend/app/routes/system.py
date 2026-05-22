from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import os

from config.database import get_db
from app.models.system import SystemModule
from app.utils.dependencies import get_current_user
from app.models.user import User
from app.services.license_service import get_current_license

router = APIRouter()

class EnabledModule(BaseModel):
    module_name: str
    is_enabled: bool

@router.get("/enabled-modules", response_model=List[EnabledModule])
async def get_enabled_modules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of enabled modules for navigation.
    A module is enabled only if BOTH the admin toggle is on AND the license includes it.
    """
    modules = db.query(SystemModule).all()

    # Get licensed features
    license_record = get_current_license(db)
    licensed_features = set()
    if license_record and license_record.features:
        licensed_features = set(license_record.features)

    result = []
    for module in modules:
        # Module is enabled only if admin enabled it AND license covers it
        # If no license exists, fall back to admin toggle only (grace/first-time setup)
        if licensed_features:
            enabled = module.is_enabled and module.module_name in licensed_features
        else:
            enabled = module.is_enabled

        result.append(EnabledModule(module_name=module.module_name, is_enabled=enabled))

    return result


@router.get("/version")
async def get_app_version():
    """Get application version. Public — no auth required."""
    from main import app as _app
    return {"version": _app.version}


@router.get("/diagnostics")
async def get_install_diagnostics(current_user: User = Depends(get_current_user)):
    """Installer-side diagnostics: desktop-shortcut outcome + schema migration
    history. Admin only.
    """
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    import json as _json
    import sys as _sys
    from app.utils.paths import get_base_dir
    from app.utils.schema_migrations import get_history, get_last_failure
    from config.database import engine as _engine

    diagnostics = {"bundled": bool(getattr(_sys, "frozen", False))}

    status_path = os.path.join(get_base_dir(), "data", ".shortcut_status.json")
    if os.path.isfile(status_path):
        try:
            with open(status_path) as f:
                diagnostics["desktop_shortcut"] = _json.load(f)
        except Exception as e:
            diagnostics["desktop_shortcut"] = {"status": "unreadable", "error": str(e)}
    else:
        diagnostics["desktop_shortcut"] = {"status": "not_attempted"}

    try:
        diagnostics["migrations"] = {
            "history": get_history(_engine, limit=20),
            "last_failure": get_last_failure(_engine),
        }
    except Exception as e:
        diagnostics["migrations"] = {"error": str(e)}

    # Upgrade history (written by launcher.check_version_bump)
    upgrade_path = os.path.join(get_base_dir(), "data", ".upgrade_history.json")
    if os.path.isfile(upgrade_path):
        try:
            with open(upgrade_path) as f:
                diagnostics["upgrade_history"] = _json.load(f)
        except Exception as e:
            diagnostics["upgrade_history"] = {"error": str(e)}
    else:
        diagnostics["upgrade_history"] = []

    version_path = os.path.join(get_base_dir(), "data", "version.txt")
    if os.path.isfile(version_path):
        try:
            with open(version_path) as f:
                diagnostics["recorded_version"] = f.read().strip()
        except Exception:
            pass

    return diagnostics


@router.get("/logs")
async def get_recent_logs(
    lines: int = 200,
    source: str = "launcher",
    current_user: User = Depends(get_current_user),
):
    """Return the last N lines of a server log file. Admin only.
    Used by the Diagnostics page for in-app log inspection without sshing
    into the box.

    source:
      'launcher' -> data/logs/launcher.log  (launcher's own logging calls)
      'server'   -> data/logs/server.log    (stdout/stderr captured when the
                    bundled exe runs windowless)
    """
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.utils.paths import get_base_dir
    filename = "server.log" if source == "server" else "launcher.log"
    log_path = os.path.join(get_base_dir(), "data", "logs", filename)
    if not os.path.isfile(log_path):
        return {"path": log_path, "source": source, "exists": False, "lines": []}

    # Cap the request so an unbounded `lines=999999` can't OOM the box
    lines = max(10, min(lines, 5000))
    try:
        # Read tail efficiently for typical log sizes (<10MB)
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-lines:]
        return {"path": log_path, "source": source, "exists": True, "lines": tail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log: {e}")


@router.get("/health-check")
async def post_install_health_check(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Green/red checklist for the post-install wizard / admin dashboard.
    Probes the load-bearing pieces of the install:
      - DB read + write
      - schema migrations have all succeeded
      - license is present and not expired
      - frontend assets are reachable (when bundled)
      - every configured backup destination is writable

    Admin only. Returns 200 even when items fail — the response payload
    carries pass/fail per check.
    """
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")

    import sys as _sys
    from app.utils.config import (
        get_configured_db_path, get_per_location_status, get_backup_locations,
    )
    from app.utils.paths import get_frontend_dir
    from app.utils.schema_migrations import get_last_failure
    from config.database import engine as _engine
    from app.services.license_service import get_current_license, compute_license_status, STATUS_EXPIRED

    checks: list[dict] = []

    def _add(name: str, ok: bool, detail: str = ""):
        checks.append({"name": name, "ok": ok, "detail": detail})

    # 1. DB readable
    db_path = get_configured_db_path()
    try:
        row = db.execute(text("SELECT 1")).first()
        _add("Database is reachable", bool(row), f"path={db_path}")
    except Exception as e:
        _add("Database is reachable", False, str(e))

    # 2. DB writable — write + read back a sentinel into a transient table
    try:
        db.execute(text("CREATE TABLE IF NOT EXISTS _health_check_probe (k TEXT PRIMARY KEY, v TEXT)"))
        db.execute(text("DELETE FROM _health_check_probe"))
        db.execute(text("INSERT INTO _health_check_probe (k, v) VALUES ('h', 'ok')"))
        db.commit()
        val = db.execute(text("SELECT v FROM _health_check_probe WHERE k='h'")).scalar()
        _add("Database is writable", val == "ok", f"sentinel={val}")
    except Exception as e:
        _add("Database is writable", False, str(e))

    # 3. Migrations all succeeded
    try:
        last_fail = get_last_failure(_engine)
        if last_fail:
            _add("Schema migrations succeeded", False,
                 f"last failure: {last_fail.get('name')} — {last_fail.get('error', '')[:200]}")
        else:
            _add("Schema migrations succeeded", True)
    except Exception as e:
        _add("Schema migrations succeeded", False, str(e))

    # 4. License present and not expired
    try:
        lic = get_current_license(db)
        if not lic:
            _add("License is installed", False, "No license found — upload one from Dashboard > License")
        else:
            status = compute_license_status(lic.expires_at)
            if status == STATUS_EXPIRED:
                _add("License is installed", False, f"License {lic.license_id} has expired")
            else:
                _add("License is installed", True, f"{lic.hospital_name} — status {status}")
    except Exception as e:
        _add("License is installed", False, str(e))

    # 5. Frontend assets reachable (only meaningful in bundled mode where the
    #    backend serves the React build)
    if getattr(_sys, "frozen", False):
        fe_index = os.path.join(get_frontend_dir(), "index.html")
        _add("Frontend assets bundled", os.path.isfile(fe_index),
             fe_index if os.path.isfile(fe_index) else f"missing: {fe_index}")
    else:
        _add("Frontend assets bundled", True, "dev mode — frontend served by react-scripts")

    # 6. Backup destinations writable (per-destination)
    locations = get_backup_locations()
    if not locations:
        _add("Backup destinations configured", False,
             "No backup locations — configure under Backup Management")
    else:
        per_loc = get_per_location_status()
        all_ok = True
        for loc in locations:
            snap = per_loc.get(loc, {})
            ok = snap.get("writable", False)
            all_ok = all_ok and ok
            _add(
                f"Backup destination writable — {loc}", ok,
                snap.get("last_error") or
                (f"last success: {snap.get('last_success')}" if snap.get("last_success") else "not yet synced"),
            )

    overall_ok = all(c["ok"] for c in checks)
    return {
        "ok": overall_ok,
        "checks": checks,
    }


@router.get("/desktop-shortcut")
async def download_desktop_shortcut(request: Request, current_user: User = Depends(get_current_user)):
    """Generate a .url shortcut file pointing to this server. Works for all users (server + LAN clients)."""
    # Determine the server URL the client should use
    # Use the Host header from the request — this is what the client used to reach us
    host = request.headers.get("host", "localhost:8000")
    scheme = request.headers.get("x-forwarded-proto", "http")
    server_url = f"{scheme}://{host}"
    icon_url = f"{server_url}/api/system/app-icon"

    # Generate Windows .url shortcut content
    url_content = (
        "[InternetShortcut]\r\n"
        f"URL={server_url}\r\n"
        f"IconFile={icon_url}\r\n"
        "IconIndex=0\r\n"
    )

    return Response(
        content=url_content,
        media_type="application/internet-shortcut",
        headers={
            "Content-Disposition": 'attachment; filename="KT HEALTH ERP.url"',
        }
    )


@router.get("/app-icon")
async def get_app_icon():
    """Serve the application icon (ico format) for desktop shortcuts."""
    from app.utils.paths import get_base_dir, get_bundle_dir
    import sys

    # Try persistent assets first (next to exe), then bundled, then dev
    search_paths = [
        os.path.join(get_base_dir(), "assets", "icon.ico"),
    ]
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        search_paths.append(os.path.join(sys._MEIPASS, "assets", "icon.ico"))
    search_paths.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "icon.ico"))

    for icon_path in search_paths:
        if os.path.isfile(icon_path):
            return Response(
                content=open(icon_path, "rb").read(),
                media_type="image/x-icon",
                headers={"Cache-Control": "public, max-age=86400"},
            )

    raise HTTPException(status_code=404, detail="Icon not found")


# ============================================================
# In-app self-update
# ============================================================

def _require_admin(current_user: User):
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/update/check")
async def update_check(current_user: User = Depends(get_current_user)):
    """Check GitHub Releases for a newer signed build. Admin only."""
    _require_admin(current_user)
    from app.services import update_service
    result = update_service.check_for_update()
    # Drop internal keys (e.g. the cached _manifest) before returning.
    return {k: v for k, v in result.items() if not k.startswith("_")}


@router.post("/update/download")
async def update_download(current_user: User = Depends(get_current_user)):
    """Start a background download of the latest installer. Admin only.
    Poll GET /update/status for progress."""
    _require_admin(current_user)
    from app.services import update_service
    return update_service.start_download()


@router.get("/update/status")
async def update_status(current_user: User = Depends(get_current_user)):
    """Current download/staging state — idle | downloading | verifying | ready | error."""
    _require_admin(current_user)
    from app.services import update_service
    return update_service.get_download_status()


@router.post("/update/apply")
async def update_apply(current_user: User = Depends(get_current_user)):
    """Launch the staged installer (one UAC prompt) and exit so it can replace
    the running binary. Windows + bundled only. Admin only."""
    _require_admin(current_user)
    from app.services import update_service
    try:
        return update_service.apply_update()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update/upload")
async def update_upload(
    installer: UploadFile = File(...),
    manifest: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Offline update path for air-gapped sites: upload an installer .exe plus
    its signed manifest.json. The manifest signature and the installer SHA-256
    are verified exactly as in the online flow. Admin only."""
    _require_admin(current_user)
    from app.services import update_service
    installer_bytes = await installer.read()
    manifest_text = (await manifest.read()).decode("utf-8", errors="replace")
    try:
        return update_service.stage_offline_update(installer_bytes, manifest_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/shutdown")
async def shutdown_server(current_user: User = Depends(get_current_user)):
    """Stop the server process. Admin only.

    The bundled exe runs windowless (no console window to close), so operators
    need an in-app way to stop it. Returns 200 immediately, then hard-exits
    ~1s later — the same handoff pattern as the self-update flow. SQLite is
    safe to stop this way: each request commits its own transaction and the
    mirror-backup thread uses the atomic .backup() API."""
    _require_admin(current_user)

    import threading
    import logging as _logging
    _logging.getLogger("launcher").warning(
        "Server shutdown requested by user '%s'",
        getattr(current_user, "username", "?"),
    )

    threading.Timer(1.0, lambda: os._exit(0)).start()
    return {"shutting_down": True}