from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional

from config.database import get_db
from app.models.hospital import Hospital
from app.models.user import User, UserRole, UserPermission
from app.models.system import SystemModule, SystemSettings
from app.utils.dependencies import get_current_user
from app.utils.auth import get_password_hash

router = APIRouter()

# Pydantic models for API requests/responses
class ModuleResponse(BaseModel):
    id: int
    module_name: str
    display_name: str
    description: Optional[str]
    is_enabled: bool
    is_always_enabled: bool
    is_licensed: bool = True

    class Config:
        from_attributes = True

class ModuleUpdate(BaseModel):
    is_enabled: bool

class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    license_number: Optional[str] = None    # For doctors
    consultation_fee_inr: Optional[str] = None  # For doctors - consultation fees in INR
    inpatient_fee_inr: Optional[str] = None     # For doctors - inpatient fees in INR  
    emergency_fee_inr: Optional[str] = None     # For doctors - emergency fees in INR
    specialization: Optional[str] = None    # For doctors
    qualification: Optional[str] = None     # For doctors
    experience_years: Optional[int] = None  # For doctors
    role_id: int
    is_active: bool = True

class UserUpdateRequest(BaseModel):
    username: Optional[str]
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    license_number: Optional[str]    # For doctors
    consultation_fee_inr: Optional[str]  # For doctors - consultation fees in INR
    inpatient_fee_inr: Optional[str]     # For doctors - inpatient fees in INR
    emergency_fee_inr: Optional[str]     # For doctors - emergency fees in INR
    specialization: Optional[str]    # For doctors
    qualification: Optional[str]     # For doctors
    experience_years: Optional[int]  # For doctors
    role_id: Optional[int]
    is_active: Optional[bool]

class UserResponse(BaseModel):
    id: int
    user_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    license_number: Optional[str] = None    # For doctors
    consultation_fee_inr: Optional[str] = None  # For doctors - consultation fees in INR
    inpatient_fee_inr: Optional[str] = None     # For doctors - inpatient fees in INR
    emergency_fee_inr: Optional[str] = None     # For doctors - emergency fees in INR
    specialization: Optional[str] = None    # For doctors  
    qualification: Optional[str] = None     # For doctors
    experience_years: Optional[int] = None  # For doctors
    is_active: bool
    user_role: dict
    user_roles: Optional[list] = None

class RoleCreateRequest(BaseModel):
    name: str
    description: Optional[str]

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    
    class Config:
        from_attributes = True

_VISIT_FEE_ROLES = {"doctor", "nurse"}


def _role_requires_visit_fee(db: Session, role_id: Optional[int]) -> bool:
    """True when the role is one for which inpatient/visit fee is mandatory (doctor or nurse)."""
    if role_id is None:
        return False
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    return bool(role and role.name in _VISIT_FEE_ROLES)


def _parse_positive_fee(value: Optional[str]) -> Optional[float]:
    """Parse a fee string and return the float if > 0, else None."""
    if value is None:
        return None
    try:
        v = float(str(value).strip())
    except (ValueError, TypeError):
        return None
    return v if v > 0 else None


def _ensure_visit_fee_for_role(db: Session, role_id: Optional[int], fee_str: Optional[str]):
    """Raise 400 if the role needs a visit fee and the supplied value is missing or non-positive."""
    if not _role_requires_visit_fee(db, role_id):
        return
    if _parse_positive_fee(fee_str) is None:
        role = db.query(UserRole).filter(UserRole.id == role_id).first()
        role_name = role.name if role else "doctor/nurse"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inpatient/visit fee (inpatient_fee_inr) is required and must be greater than 0 for {role_name} users."
        )


def require_super_admin(current_user: User = Depends(get_current_user)):
    """Dependency to ensure only super admin can access these endpoints"""
    if not current_user.has_role('super_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user

def require_admin_access(current_user: User = Depends(get_current_user)):
    """Dependency for super admin or hospital admin access"""
    if not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

@router.get("/super-dashboard")
async def get_super_admin_dashboard(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """System-level dashboard for super admin."""
    from sqlalchemy import func as sql_func, distinct
    from datetime import date, timedelta, datetime
    from app.models.audit import AuditLog
    from app.models.system import SystemModule
    from app.models.license import License

    today = date.today()
    now = datetime.now()
    week_ago = today - timedelta(days=7)

    # --- Users ---
    total_users = db.query(sql_func.count(User.id)).scalar() or 0
    active_users = db.query(sql_func.count(User.id)).filter(User.is_active == True).scalar() or 0
    inactive_users = total_users - active_users

    # Users by role
    role_breakdown = {}
    all_users = db.query(User).filter(User.is_active == True).all()
    for u in all_users:
        rname = u.role.name if u.role else "unknown"
        role_breakdown[rname] = role_breakdown.get(rname, 0) + 1

    # --- Active sessions (users who logged in today via audit logs) ---
    logged_in_today = 0
    recent_logins = []
    try:
        logged_in_today = db.query(sql_func.count(distinct(AuditLog.user_id))).filter(
            sql_func.date(AuditLog.timestamp) == today,
            AuditLog.action == "login"
        ).scalar() or 0

        logins = db.query(AuditLog).filter(
            AuditLog.action == "login",
            sql_func.date(AuditLog.timestamp) == today
        ).order_by(AuditLog.timestamp.desc()).limit(10).all()
        recent_logins = [
            {"user_name": l.user_name, "user_role": l.user_role or "", "time": l.timestamp.isoformat() if l.timestamp else "", "ip": l.ip_address or ""}
            for l in logins
        ]
    except Exception:
        pass

    # --- Audit summary ---
    total_audit_logs = 0
    today_audit_logs = 0
    audit_categories = {}
    try:
        total_audit_logs = db.query(sql_func.count(AuditLog.id)).scalar() or 0
        today_audit_logs = db.query(sql_func.count(AuditLog.id)).filter(
            sql_func.date(AuditLog.timestamp) == today
        ).scalar() or 0
        cats = db.query(AuditLog.category, sql_func.count(AuditLog.id)).filter(
            sql_func.date(AuditLog.timestamp) >= week_ago
        ).group_by(AuditLog.category).all()
        audit_categories = {c: n for c, n in cats if c}
    except Exception:
        pass

    # --- License ---
    license_info = {"status": "no_license", "days_remaining": 0, "plan": None, "expires_at": None}
    try:
        lic = db.query(License).order_by(License.id.desc()).first()
        if lic:
            days_left = (lic.expires_at - now).days if lic.expires_at else 0
            license_info = {
                "status": "active" if days_left > 30 else ("expiring_soon" if days_left > 0 else "expired"),
                "days_remaining": days_left,
                "plan": lic.plan,
                "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
                "hospital_name": lic.hospital_name,
                "max_users": lic.max_users,
            }
    except Exception:
        pass

    # --- Modules ---
    modules = []
    try:
        mods = db.query(SystemModule).all()
        modules = [{"name": m.module_name, "display_name": m.display_name, "enabled": m.is_enabled, "always_on": m.is_always_enabled} for m in mods]
    except Exception:
        pass

    # --- Activity trend (last 7 days) ---
    daily_activity = []
    try:
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            count = db.query(sql_func.count(AuditLog.id)).filter(
                sql_func.date(AuditLog.timestamp) == d
            ).scalar() or 0
            daily_activity.append({"date": d.isoformat(), "day": d.strftime("%a"), "count": count})
    except Exception:
        pass

    # --- Recent system actions ---
    recent_actions = []
    try:
        actions = db.query(AuditLog).filter(
            AuditLog.category.in_(["admin", "auth", "billing"])
        ).order_by(AuditLog.timestamp.desc()).limit(8).all()
        recent_actions = [
            {"user_name": a.user_name, "action": a.action, "category": a.category,
             "description": a.description, "time": a.timestamp.isoformat() if a.timestamp else ""}
            for a in actions
        ]
    except Exception:
        pass

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "inactive": inactive_users,
            "logged_in_today": logged_in_today,
            "by_role": role_breakdown,
        },
        "license": license_info,
        "modules": modules,
        "audit": {
            "total_logs": total_audit_logs,
            "today_logs": today_audit_logs,
            "categories_this_week": audit_categories,
            "daily_activity": daily_activity,
        },
        "recent_logins": recent_logins,
        "recent_actions": recent_actions,
    }


# MODULE MANAGEMENT ENDPOINTS
@router.get("/modules", response_model=List[ModuleResponse])
async def get_system_modules(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Get all system modules with their enable/disable status and license info"""
    from app.services.license_service import get_current_license
    modules = db.query(SystemModule).all()

    license_record = get_current_license(db)
    licensed_features = set()
    if license_record and license_record.features:
        licensed_features = set(license_record.features)

    result = []
    for module in modules:
        resp = ModuleResponse.model_validate(module)
        # Always-enabled modules are always considered licensed
        # If license exists, check if module is in licensed features
        # If no license yet, treat all as licensed (first-time setup grace)
        if module.is_always_enabled:
            resp.is_licensed = True
        elif licensed_features:
            resp.is_licensed = module.module_name in licensed_features
        else:
            resp.is_licensed = True
        result.append(resp)

    return result

@router.put("/modules/{module_id}", response_model=ModuleResponse)
async def update_module_status(
    module_id: int,
    module_update: ModuleUpdate,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Enable or disable a module"""
    module = db.query(SystemModule).filter(SystemModule.id == module_id).first()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found"
        )
    
    # Prevent disabling always-enabled modules
    if module.is_always_enabled and not module_update.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Module '{module.display_name}' cannot be disabled"
        )

    # Prevent enabling unlicensed modules
    if module_update.is_enabled:
        from app.services.license_service import get_current_license
        license_record = get_current_license(db)
        if license_record and license_record.features:
            if module.module_name not in license_record.features:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Module '{module.display_name}' is not included in your license"
                )

    module.is_enabled = module_update.is_enabled
    db.commit()
    db.refresh(module)
    return module

# USER MANAGEMENT ENDPOINTS
@router.get("/user-limit")
async def get_user_limit(
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Get current user count vs license limit."""
    from app.services.license_service import get_current_license
    license_record = get_current_license(db)
    max_users = license_record.max_users if license_record and license_record.max_users else 0

    super_admin_role = db.query(UserRole).filter(UserRole.name == 'super_admin').first()
    active_count = db.query(User).filter(
        User.is_active == True,
        User.role_id != (super_admin_role.id if super_admin_role else -1)
    ).count()

    return {
        "active_users": active_count,
        "max_users": max_users,
        "remaining": max(max_users - active_count, 0) if max_users else None,
        "unlimited": max_users == 0,
    }


@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Get all users in the system"""
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            license_number=user.license_number,
        consultation_fee_inr=user.consultation_fee_inr,
        inpatient_fee_inr=user.inpatient_fee_inr,
        emergency_fee_inr=user.emergency_fee_inr,
            specialization=user.specialization,
            qualification=user.qualification,
            experience_years=user.experience_years,
            is_active=user.is_active,
            user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description},
        user_roles=[{"id": r.id, "name": r.name} for r in user.roles] if user.roles else [{"id": user.role.id, "name": user.role.name}]
        )
        for user in users
    ]

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreateRequest,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Create a new user"""
    # Check user limit from license
    from app.services.license_service import get_current_license
    license_record = get_current_license(db)
    if license_record and license_record.max_users:
        super_admin_role = db.query(UserRole).filter(UserRole.name == 'super_admin').first()
        active_count = db.query(User).filter(
            User.is_active == True,
            User.role_id != (super_admin_role.id if super_admin_role else -1)
        ).count()
        if active_count >= license_record.max_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User limit reached ({active_count}/{license_record.max_users}). Upgrade your license to add more users."
            )

    # Check if username or email already exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    # Verify role exists
    role = db.query(UserRole).filter(UserRole.id == user_data.role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role not found"
        )

    # super_admin can only be created via the install seed, never through the API
    if role.name == 'super_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="super_admin users cannot be created through this form"
        )

    # Doctor/nurse users must have a positive inpatient/visit fee.
    _ensure_visit_fee_for_role(db, user_data.role_id, user_data.inpatient_fee_inr)

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        license_number=user_data.license_number,
        consultation_fee_inr=user_data.consultation_fee_inr,
        inpatient_fee_inr=user_data.inpatient_fee_inr,
        emergency_fee_inr=user_data.emergency_fee_inr,
        specialization=user_data.specialization,
        qualification=user_data.qualification,
        experience_years=user_data.experience_years,
        role_id=user_data.role_id,
        is_active=user_data.is_active,
        hospital_id=1  # Single hospital system
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)

    # Audit log
    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "create_user", "admin", "User", user.id,
            f"Created user: {user.first_name} {user.last_name} (@{user.username}), Role: {user.role.name}",
            details={"username": user.username, "email": user.email, "role": user.role.name})
    except Exception:
        pass

    return UserResponse(
        id=user.id,
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        license_number=user.license_number,
        consultation_fee_inr=user.consultation_fee_inr,
        inpatient_fee_inr=user.inpatient_fee_inr,
        emergency_fee_inr=user.emergency_fee_inr,
        specialization=user.specialization,
        qualification=user.qualification,
        experience_years=user.experience_years,
        is_active=user.is_active,
        user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description},
        user_roles=[{"id": r.id, "name": r.name} for r in user.roles] if user.roles else [{"id": user.role.id, "name": user.role.name}]
    )

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdateRequest,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Update an existing user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields that are provided
    if user_data.username is not None:
        # Check if new username already exists (excluding current user)
        existing_user = db.query(User).filter(
            User.username == user_data.username,
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        user.username = user_data.username
    
    if user_data.email is not None:
        # Check if new email already exists (excluding current user)
        existing_user = db.query(User).filter(
            User.email == user_data.email,
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
        user.email = user_data.email
    
    if user_data.first_name is not None:
        user.first_name = user_data.first_name
    if user_data.last_name is not None:
        user.last_name = user_data.last_name
    if user_data.phone is not None:
        user.phone = user_data.phone
    if user_data.license_number is not None:
        user.license_number = user_data.license_number
    if user_data.consultation_fee_inr is not None:
        user.consultation_fee_inr = user_data.consultation_fee_inr
    if user_data.inpatient_fee_inr is not None:
        user.inpatient_fee_inr = user_data.inpatient_fee_inr
    if user_data.emergency_fee_inr is not None:
        user.emergency_fee_inr = user_data.emergency_fee_inr
    if user_data.specialization is not None:
        user.specialization = user_data.specialization
    if user_data.qualification is not None:
        user.qualification = user_data.qualification
    if user_data.experience_years is not None:
        user.experience_years = user_data.experience_years
    if user_data.role_id is not None:
        # Verify role exists
        role = db.query(UserRole).filter(UserRole.id == user_data.role_id).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role not found"
            )
        # Prevent assigning super_admin via the API — it is seeded only.
        if role.name == 'super_admin' and not user.has_role('super_admin'):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="super_admin cannot be assigned through this form"
            )
        user.role_id = user_data.role_id
    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    # If the resulting role is doctor/nurse, the inpatient fee must be set and > 0.
    _ensure_visit_fee_for_role(db, user.role_id, user.inpatient_fee_inr)

    db.commit()
    db.refresh(user)
    
    return UserResponse(
        id=user.id,
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        license_number=user.license_number,
        consultation_fee_inr=user.consultation_fee_inr,
        inpatient_fee_inr=user.inpatient_fee_inr,
        emergency_fee_inr=user.emergency_fee_inr,
        specialization=user.specialization,
        qualification=user.qualification,
        experience_years=user.experience_years,
        is_active=user.is_active,
        user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description},
        user_roles=[{"id": r.id, "name": r.name} for r in user.roles] if user.roles else [{"id": user.role.id, "name": user.role.name}]
    )

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=4)


@router.put("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    data: ResetPasswordRequest,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Reset a user's password. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only super_admin can reset another super_admin's password
    user_roles = [r.name for r in user.roles] if user.roles else [user.role.name]
    if 'super_admin' in user_roles and not any(r in current_user.role_names for r in ['super_admin']):
        raise HTTPException(status_code=403, detail="Only super admin can reset another super admin's password")

    user.password_hash = get_password_hash(data.new_password)
    # Force the recipient to choose their own password on next login
    user.must_change_password = True
    db.commit()

    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "reset_password", "admin", "User", user.id,
            f"Reset password for user {user.username}",
            details={"target_user": user.username})
    except Exception:
        pass

    return {"message": f"Password reset successfully for {user.username}"}


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: int, data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Assign multiple roles to a user."""
    require_admin_access(current_user)
    from app.models.user import user_role_association
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role_ids = data.get('role_ids', [])
    if not role_ids:
        raise HTTPException(status_code=400, detail="At least one role is required")

    # Verify all roles exist
    roles = db.query(UserRole).filter(UserRole.id.in_(role_ids)).all()
    if len(roles) != len(role_ids):
        raise HTTPException(status_code=400, detail="One or more roles not found")

    # Prevent granting super_admin via the API to a user that doesn't already hold it
    if any(r.name == 'super_admin' for r in roles) and not user.has_role('super_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="super_admin cannot be assigned through this form"
        )

    # Update primary role_id to the first role
    user.role_id = role_ids[0]
    # Update many-to-many
    user.roles = roles

    db.commit()
    db.refresh(user)
    return {
        "message": "Roles updated",
        "roles": [{"id": r.id, "name": r.name} for r in user.roles],
    }

@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all roles assigned to a user."""
    require_admin_access(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user.id,
        "primary_role": {"id": user.role.id, "name": user.role.name},
        "roles": [{"id": r.id, "name": r.name} for r in user.roles] if user.roles else [{"id": user.role.id, "name": user.role.name}],
    }

@router.delete("/users/{user_id}")
async def archive_user(
    user_id: int,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Archive a user (set is_active=False). Does not delete from DB."""
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot archive your own account"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.has_role('super_admin'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot archive a super admin account"
        )

    user.is_active = False
    db.commit()
    return {"message": "User archived successfully"}


@router.put("/users/{user_id}/restore")
async def restore_user(
    user_id: int,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Restore an archived user (set is_active=True)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = True
    db.commit()
    return {"message": "User restored successfully"}

# ---------------------------------------------------------------------------
# Bulk user import (doctors / nurses) — CSV upload
# ---------------------------------------------------------------------------
#
# Installer-time "normal users" bulk import lives in the Inno Setup wizard
# (see app.services.bootstrap_from_seed). Doctors and nurses are intentionally
# excluded from that path because they have role-specific profile columns
# (specialization, license number, default consultation duration, etc) and
# benefit from being added after the hospital is up and running.
#
# Both endpoints share the same pattern: read the upload, run the role-
# specific validator, and BLOCK the whole batch if any row fails — duplicates
# never apply partially. The frontend is expected to surface row-level errors
# from the response.

CSV_MAX_BYTES = 1 * 1024 * 1024  # 1 MB — generous for 5k rows


async def _read_csv_upload(file: UploadFile) -> str:
    raw = await file.read()
    if len(raw) > CSV_MAX_BYTES:
        raise HTTPException(status_code=413, detail="CSV file too large (max 1 MB)")
    try:
        # Tolerate Excel-saved UTF-8 BOM.
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")


def _resolve_hospital_id(db: Session) -> int:
    hospital = db.query(Hospital).first()
    if hospital is None:
        raise HTTPException(status_code=500, detail="No hospital row in DB — finish setup first")
    return hospital.id


@router.post("/users/bulk-import-doctors")
async def bulk_import_doctors(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db),
):
    """Bulk-create doctor users from a CSV upload.

    Required columns: username, email, first_name, last_name, password,
    specialization, license_number. Optional: phone, qualification,
    consultation_fee_inr, inpatient_fee_inr, emergency_fee_inr,
    experience_years, default_consultation_duration.
    """
    from app.services.user_csv_import import (
        apply_doctors,
        parse_and_validate_doctors,
    )

    csv_text = await _read_csv_upload(file)
    existing_usernames = [u for (u,) in db.query(User.username).all()]
    existing_emails = [e for (e,) in db.query(User.email).all()]

    rows, errors = parse_and_validate_doctors(
        csv_text,
        existing_usernames=existing_usernames,
        existing_emails=existing_emails,
    )
    if errors:
        return {
            "ok": False,
            "created": 0,
            "errors": [e.as_dict() for e in errors],
        }

    hospital_id = _resolve_hospital_id(db)
    try:
        result = apply_doctors(db, rows, hospital_id)
    except ValueError as e:
        return {"ok": False, "created": 0, "errors": [{"line": None, "field": None, "message": str(e)}]}

    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "bulk_import_doctors", "admin", "User", None,
                   f"Bulk-imported {result['created']} doctor(s) from CSV",
                   details={"usernames": result["usernames"]})
    except Exception:
        pass

    return {"ok": True, "created": result["created"], "usernames": result["usernames"], "errors": []}


@router.post("/users/bulk-import-nurses")
async def bulk_import_nurses(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db),
):
    """Bulk-create nurse users from a CSV upload.

    Required columns: username, email, first_name, last_name, password.
    Optional: phone.
    """
    from app.services.user_csv_import import (
        apply_nurses,
        parse_and_validate_nurses,
    )

    csv_text = await _read_csv_upload(file)
    existing_usernames = [u for (u,) in db.query(User.username).all()]
    existing_emails = [e for (e,) in db.query(User.email).all()]

    rows, errors = parse_and_validate_nurses(
        csv_text,
        existing_usernames=existing_usernames,
        existing_emails=existing_emails,
    )
    if errors:
        return {
            "ok": False,
            "created": 0,
            "errors": [e.as_dict() for e in errors],
        }

    hospital_id = _resolve_hospital_id(db)
    try:
        result = apply_nurses(db, rows, hospital_id)
    except ValueError as e:
        return {"ok": False, "created": 0, "errors": [{"line": None, "field": None, "message": str(e)}]}

    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "bulk_import_nurses", "admin", "User", None,
                   f"Bulk-imported {result['created']} nurse(s) from CSV",
                   details={"usernames": result["usernames"]})
    except Exception:
        pass

    return {"ok": True, "created": result["created"], "usernames": result["usernames"], "errors": []}


@router.get("/users/bulk-import-sample/{role}")
async def bulk_import_sample(
    role: str,
    current_user: User = Depends(require_admin_access),
):
    """Return a sample CSV body for the given role. Used by the in-app
    importer UI to give operators a known-good template they can edit."""
    from fastapi import Response
    if role == "doctor":
        body = (
            "username,email,first_name,last_name,password,phone,"
            "specialization,license_number,qualification,consultation_fee_inr,"
            "inpatient_fee_inr,emergency_fee_inr,experience_years,"
            "default_consultation_duration\n"
            "drravi,drravi@hospital.in,Ravi,Kumar,Welcome@123,9876543210,"
            "Cardiology,MCI-12345,MBBS MD,800,2000,1500,12,15\n"
            "drmeera,drmeera@hospital.in,Meera,Iyer,Welcome@123,9876543211,"
            "Pediatrics,MCI-67890,MBBS MD DCH,600,1500,1200,8,20\n"
        )
        filename = "doctors_sample.csv"
    elif role == "nurse":
        body = (
            "username,email,first_name,last_name,password,phone\n"
            "asha,asha.n@hospital.in,Asha,Menon,Welcome@123,9876543220\n"
            "priya,priya.n@hospital.in,Priya,Rao,Welcome@123,9876543221\n"
        )
        filename = "nurses_sample.csv"
    else:
        raise HTTPException(status_code=404, detail=f"No sample for role {role!r}")
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ROLE MANAGEMENT ENDPOINTS
@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles(
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db)
):
    """Get all user roles"""
    roles = db.query(UserRole).all()
    return roles

@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreateRequest,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Create a new role (Super admin only)"""
    # Check if role name already exists
    if db.query(UserRole).filter(UserRole.name == role_data.name).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role name already exists"
        )
    
    role = UserRole(
        name=role_data.name,
        description=role_data.description
    )
    
    db.add(role)
    db.commit()
    db.refresh(role)
    return role

@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleCreateRequest,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Update a role (Super admin only)"""
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Check if new role name already exists (excluding current role)
    existing_role = db.query(UserRole).filter(
        UserRole.name == role_data.name,
        UserRole.id != role_id
    ).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role name already exists"
        )
    
    role.name = role_data.name
    role.description = role_data.description
    
    db.commit()
    db.refresh(role)
    return role

@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Delete a role (Super admin only)"""
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Check if role is in use
    user_count = db.query(User).filter(User.role_id == role_id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role: {user_count} users are assigned to this role"
        )
    
    db.delete(role)
    db.commit()
    return {"message": "Role deleted successfully"}


# ============================================================
# Role-permission management (granular per-feature auth)
# ============================================================

class ModulePermissionResponse(BaseModel):
    id: int
    module_name: str
    permission_name: str
    permission_description: Optional[str] = None
    category: Optional[str] = None

    class Config:
        from_attributes = True


class RolePermissionsByModule(BaseModel):
    module_name: str
    permissions: List[str]  # permission_name strings the role has


class RolePermissionsResponse(BaseModel):
    role_id: int
    role_name: str
    grants: List[RolePermissionsByModule]


class RolePermissionsUpdate(BaseModel):
    module_name: str
    permissions: List[str]


@router.get("/me/permissions")
async def get_my_permissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Effective permissions for the current user, grouped by module.

    Used by the frontend to gate UI elements (hide/disable buttons the user
    can't act on). Super_admin and hospital_admin get a wildcard `["*"]`
    against every module, mirroring the bypass that
    `require_feature_permission` and `require_permission` honour.
    """
    from app.models.permissions import RoleModulePermission
    from app.utils.auth import UserRoles
    user_roles = set(current_user.role_names)
    if {UserRoles.SUPER_ADMIN, UserRoles.HOSPITAL_ADMIN} & user_roles:
        return {"is_admin": True, "roles": list(user_roles), "modules": {"*": ["*"]}}

    role_ids = [r.id for r in (current_user.roles or [])]
    if current_user.role_id and current_user.role_id not in role_ids:
        role_ids.append(current_user.role_id)

    grants = db.query(RoleModulePermission).filter(
        RoleModulePermission.role_id.in_(role_ids)
    ).all()
    modules: dict[str, set[str]] = {}
    for g in grants:
        if not g.permissions:
            continue
        modules.setdefault(g.module_name, set()).update(g.permissions)
    return {
        "is_admin": False,
        "roles": list(user_roles),
        "modules": {m: sorted(perms) for m, perms in modules.items()},
    }


@router.get("/module-permissions", response_model=List[ModulePermissionResponse])
async def list_module_permissions(
    module_name: Optional[str] = None,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db),
):
    """Catalog of all defined module permissions (the vocabulary)."""
    from app.models.permissions import ModulePermission
    q = db.query(ModulePermission)
    if module_name:
        q = q.filter(ModulePermission.module_name == module_name)
    return q.order_by(ModulePermission.module_name, ModulePermission.permission_name).all()


@router.get("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
async def get_role_permissions(
    role_id: int,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db),
):
    """Get all module-permission grants for a role."""
    from app.models.permissions import RoleModulePermission
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    rows = db.query(RoleModulePermission).filter(
        RoleModulePermission.role_id == role_id
    ).all()
    grants = [
        RolePermissionsByModule(module_name=r.module_name, permissions=list(r.permissions or []))
        for r in rows
    ]
    return RolePermissionsResponse(
        role_id=role.id, role_name=role.name, grants=grants,
    )


@router.put("/roles/{role_id}/permissions", response_model=RolePermissionsByModule)
async def update_role_permissions(
    role_id: int,
    data: RolePermissionsUpdate,
    current_user: User = Depends(require_admin_access),
    db: Session = Depends(get_db),
):
    """Replace the permission list for (role, module) with the provided set."""
    from app.models.permissions import RoleModulePermission, ModulePermission
    role = db.query(UserRole).filter(UserRole.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.name in ("super_admin", "hospital_admin"):
        raise HTTPException(
            status_code=400,
            detail=f"'{role.name}' bypasses permission checks; its grants cannot be narrowed",
        )

    # Validate each requested permission exists in the catalog for that module
    catalog = {
        p.permission_name for p in db.query(ModulePermission).filter(
            ModulePermission.module_name == data.module_name
        ).all()
    }
    unknown = [p for p in data.permissions if p not in catalog]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown permissions for module '{data.module_name}': {', '.join(unknown)}",
        )

    existing = db.query(RoleModulePermission).filter(
        RoleModulePermission.role_id == role_id,
        RoleModulePermission.module_name == data.module_name,
    ).first()
    previous = list(existing.permissions or []) if existing else []

    if existing:
        existing.permissions = data.permissions
    else:
        existing = RoleModulePermission(
            role_id=role_id,
            module_name=data.module_name,
            permissions=data.permissions,
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)

    # Audit
    added = sorted(set(data.permissions) - set(previous))
    removed = sorted(set(previous) - set(data.permissions))
    try:
        from app.services.audit_service import log_action
        log_action(
            db, current_user, "update_role_permissions", "admin",
            "RoleModulePermission", existing.id,
            f"Updated '{role.name}' permissions on '{data.module_name}': +{len(added)} / -{len(removed)}",
            details={"role": role.name, "module": data.module_name,
                     "added": added, "removed": removed},
        )
    except Exception:
        pass

    return RolePermissionsByModule(module_name=existing.module_name, permissions=list(existing.permissions or []))