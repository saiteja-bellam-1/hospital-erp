from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

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