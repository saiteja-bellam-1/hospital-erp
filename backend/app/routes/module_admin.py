from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json

from config.database import get_db
from app.models.user import User
from app.models.permissions import ModuleRates, ModuleTemplate, HospitalSettings, RoleModulePermission
from app.utils.dependencies import get_current_user

router = APIRouter()

# Pydantic models
class RateCreateRequest(BaseModel):
    service_name: str
    service_code: Optional[str]
    base_rate: str
    discounted_rate: Optional[str]
    description: Optional[str]

class RateUpdateRequest(BaseModel):
    service_name: Optional[str]
    service_code: Optional[str]
    base_rate: Optional[str]
    discounted_rate: Optional[str]
    description: Optional[str]
    is_active: Optional[bool]

class RateResponse(BaseModel):
    id: int
    module_name: str
    service_name: str
    service_code: Optional[str]
    base_rate: str
    discounted_rate: Optional[str]
    description: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

class TemplateCreateRequest(BaseModel):
    template_name: str
    template_type: str
    template_data: Dict[str, Any]

class TemplateResponse(BaseModel):
    id: int
    module_name: str
    template_name: str
    template_type: str
    template_data: Dict[str, Any]
    is_active: bool
    
    class Config:
        from_attributes = True

class SettingRequest(BaseModel):
    setting_key: str
    setting_value: str
    setting_type: str = "string"
    description: Optional[str]

class SettingResponse(BaseModel):
    id: int
    setting_category: str
    setting_key: str
    setting_value: str
    setting_type: str
    description: Optional[str]
    
    class Config:
        from_attributes = True

def check_module_permission(user: User, module_name: str, required_permission: str, db: Session):
    """Check if user has specific permission for a module"""
    if user.role.name == 'super_admin':
        return True
    
    role_permissions = db.query(RoleModulePermission).filter(
        RoleModulePermission.role_id == user.role.id,
        RoleModulePermission.module_name == module_name
    ).first()
    
    if not role_permissions:
        return False
        
    try:
        permissions = json.loads(role_permissions.permissions) if isinstance(role_permissions.permissions, str) else role_permissions.permissions
        return required_permission in permissions
    except:
        return False

def require_module_admin(module_name: str, permission: str):
    """Dependency factory for module-specific admin permissions"""
    def check_permission(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if not check_module_permission(current_user, module_name, permission, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {module_name} module"
            )
        return current_user
    return check_permission

# RATES MANAGEMENT ENDPOINTS
@router.get("/{module_name}/rates", response_model=List[RateResponse])
async def get_module_rates(
    module_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get rates for a specific module"""
    if not check_module_permission(current_user, module_name, "set_rates", db) and \
       not check_module_permission(current_user, module_name, "manage_rates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    rates = db.query(ModuleRates).filter(ModuleRates.module_name == module_name).all()
    return rates

@router.post("/{module_name}/rates", response_model=RateResponse)
async def create_module_rate(
    module_name: str,
    rate_data: RateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new rate for a module"""
    if not check_module_permission(current_user, module_name, "set_rates", db) and \
       not check_module_permission(current_user, module_name, "manage_rates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    rate = ModuleRates(
        module_name=module_name,
        service_name=rate_data.service_name,
        service_code=rate_data.service_code,
        base_rate=rate_data.base_rate,
        discounted_rate=rate_data.discounted_rate,
        description=rate_data.description,
        created_by=current_user.id
    )
    
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate

@router.put("/{module_name}/rates/{rate_id}", response_model=RateResponse)
async def update_module_rate(
    module_name: str,
    rate_id: int,
    rate_data: RateUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a module rate"""
    if not check_module_permission(current_user, module_name, "set_rates", db) and \
       not check_module_permission(current_user, module_name, "manage_rates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    rate = db.query(ModuleRates).filter(
        ModuleRates.id == rate_id,
        ModuleRates.module_name == module_name
    ).first()
    
    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")
    
    # Update fields
    if rate_data.service_name is not None:
        rate.service_name = rate_data.service_name
    if rate_data.service_code is not None:
        rate.service_code = rate_data.service_code
    if rate_data.base_rate is not None:
        rate.base_rate = rate_data.base_rate
    if rate_data.discounted_rate is not None:
        rate.discounted_rate = rate_data.discounted_rate
    if rate_data.description is not None:
        rate.description = rate_data.description
    if rate_data.is_active is not None:
        rate.is_active = rate_data.is_active
    
    db.commit()
    db.refresh(rate)
    return rate

@router.delete("/{module_name}/rates/{rate_id}")
async def delete_module_rate(
    module_name: str,
    rate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a module rate"""
    if not check_module_permission(current_user, module_name, "set_rates", db) and \
       not check_module_permission(current_user, module_name, "manage_rates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    rate = db.query(ModuleRates).filter(
        ModuleRates.id == rate_id,
        ModuleRates.module_name == module_name
    ).first()
    
    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found")
    
    db.delete(rate)
    db.commit()
    return {"message": "Rate deleted successfully"}

# TEMPLATES MANAGEMENT ENDPOINTS
@router.get("/{module_name}/templates", response_model=List[TemplateResponse])
async def get_module_templates(
    module_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get templates for a specific module"""
    if not check_module_permission(current_user, module_name, "manage_templates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    templates = db.query(ModuleTemplate).filter(ModuleTemplate.module_name == module_name).all()
    
    # Convert template_data from JSON string to dict if needed
    result = []
    for template in templates:
        template_dict = template.__dict__.copy()
        if isinstance(template.template_data, str):
            try:
                template_dict['template_data'] = json.loads(template.template_data)
            except:
                template_dict['template_data'] = {}
        result.append(TemplateResponse(**template_dict))
    
    return result

@router.post("/{module_name}/templates", response_model=TemplateResponse)
async def create_module_template(
    module_name: str,
    template_data: TemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new template for a module"""
    if not check_module_permission(current_user, module_name, "manage_templates", db):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    template = ModuleTemplate(
        module_name=module_name,
        template_name=template_data.template_name,
        template_type=template_data.template_type,
        template_data=json.dumps(template_data.template_data),
        created_by=current_user.id
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    # Return with parsed template_data
    result = template.__dict__.copy()
    result['template_data'] = template_data.template_data
    return TemplateResponse(**result)

# SETTINGS MANAGEMENT ENDPOINTS  
@router.get("/{module_name}/settings", response_model=List[SettingResponse])
async def get_module_settings(
    module_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get settings for a specific module"""
    if not check_module_permission(current_user, module_name, "manage_settings", db):
        # Allow viewing settings for module admins
        admin_permissions = ["set_rates", "manage_rates", "manage_templates", "manage_inventory", "manage_beds"]
        has_admin_permission = any(check_module_permission(current_user, module_name, perm, db) for perm in admin_permissions)
        
        if not has_admin_permission:
            raise HTTPException(status_code=403, detail="Permission denied")
    
    settings = db.query(HospitalSettings).filter(HospitalSettings.setting_category == module_name).all()
    return settings

@router.post("/{module_name}/settings", response_model=SettingResponse)
async def create_module_setting(
    module_name: str,
    setting_data: SettingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a module setting"""
    # Check for admin permission in the module
    admin_permissions = ["set_rates", "manage_rates", "manage_templates", "manage_inventory", "manage_beds", "manage_settings"]
    has_admin_permission = any(check_module_permission(current_user, module_name, perm, db) for perm in admin_permissions)
    
    if not has_admin_permission:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    # Check if setting already exists
    existing_setting = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == module_name,
        HospitalSettings.setting_key == setting_data.setting_key
    ).first()
    
    if existing_setting:
        # Update existing
        existing_setting.setting_value = setting_data.setting_value
        existing_setting.setting_type = setting_data.setting_type
        existing_setting.description = setting_data.description
        db.commit()
        db.refresh(existing_setting)
        return existing_setting
    else:
        # Create new
        setting = HospitalSettings(
            setting_category=module_name,
            setting_key=setting_data.setting_key,
            setting_value=setting_data.setting_value,
            setting_type=setting_data.setting_type,
            description=setting_data.description,
            created_by=current_user.id
        )
        
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return setting

# PERMISSIONS CHECK ENDPOINT
@router.get("/{module_name}/permissions")
async def get_user_module_permissions(
    module_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's permissions for a specific module"""
    if current_user.role.name == 'super_admin':
        return {"permissions": ["all"], "role": "super_admin"}
    
    role_permissions = db.query(RoleModulePermission).filter(
        RoleModulePermission.role_id == current_user.role.id,
        RoleModulePermission.module_name == module_name
    ).first()
    
    if not role_permissions:
        return {"permissions": [], "role": current_user.role.name}
    
    try:
        permissions = json.loads(role_permissions.permissions) if isinstance(role_permissions.permissions, str) else role_permissions.permissions
        return {"permissions": permissions, "role": current_user.role.name}
    except:
        return {"permissions": [], "role": current_user.role.name}