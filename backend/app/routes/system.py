from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
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