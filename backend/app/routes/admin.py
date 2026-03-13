from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from config.database import get_db
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

class RoleCreateRequest(BaseModel):
    name: str
    description: Optional[str]

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    
    class Config:
        from_attributes = True

def require_super_admin(current_user: User = Depends(get_current_user)):
    """Dependency to ensure only super admin can access these endpoints"""
    if current_user.role.name != 'super_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user

def require_admin_access(current_user: User = Depends(get_current_user)):
    """Dependency for super admin or hospital admin access"""
    if current_user.role.name not in ['super_admin', 'hospital_admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# MODULE MANAGEMENT ENDPOINTS
@router.get("/modules", response_model=List[ModuleResponse])
async def get_system_modules(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """Get all system modules with their enable/disable status"""
    modules = db.query(SystemModule).all()
    return modules

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
    
    module.is_enabled = module_update.is_enabled
    db.commit()
    db.refresh(module)
    return module

# USER MANAGEMENT ENDPOINTS
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
            user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description}
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
        user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description}
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
        user.role_id = user_data.role_id
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
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
        user_role={"id": user.role.id, "name": user.role.name, "description": user.role.description}
    )

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

    if user.role.name == 'super_admin':
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