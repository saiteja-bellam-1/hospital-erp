from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from config.database import get_db
from app.models.user import User, UserRole
from app.utils.auth import verify_password, create_access_token, get_password_hash
from app.utils.dependencies import get_current_user
from app.services.license_service import is_license_valid_for_login, get_license_status

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int  # Integer ID used for database relationships
    user_id: str
    username: str
    email: str
    full_name: str
    role: str  # Primary role (backward compat)
    roles: List[str] = []  # All assigned roles
    hospital_id: Optional[int]
    is_active: bool

class LicenseInfo(BaseModel):
    status: str
    message: str
    days_remaining: int
    features: list = []
    expires_at: Optional[str] = None
    max_users: int = 0
    seller_info: Optional[dict] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    license: Optional[LicenseInfo] = None

@router.post("/login", response_model=TokenResponse)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    # Find user by username
    user = db.query(User).filter(User.username == user_credentials.username).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Verify password
    if not verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Check license validity — check all roles, allow if ANY role is permitted
    license_allowed = False
    license_reason = ""
    for role_name in user.role_names:
        allowed, reason = is_license_valid_for_login(db, role_name)
        if allowed:
            license_allowed = True
            break
        license_reason = reason
    if not license_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=license_reason
        )

    # Log successful login
    try:
        from app.services.audit_service import log_action
        log_action(db, user, "login", "auth", "User", user.id,
                   f"{user.first_name} {user.last_name} logged in")
    except Exception:
        pass

    # Create access token
    access_token = create_access_token(data={"sub": user.username})
    
    # Prepare user response
    user_response = UserResponse(
        id=user.id,
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        full_name=f"{user.first_name} {user.last_name}",
        role=user.role.name,
        roles=user.role_names,
        hospital_id=user.hospital_id,
        is_active=user.is_active
    )
    
    # Get license info
    lic_status = get_license_status(db)
    license_info = LicenseInfo(
        status=lic_status["status"],
        message=lic_status["message"],
        days_remaining=lic_status["days_remaining"],
        features=lic_status.get("features", []),
        expires_at=lic_status.get("expires_at"),
        max_users=lic_status.get("max_users", 0),
        seller_info=lic_status.get("seller_info"),
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_response,
        license=license_info,
    )

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        full_name=f"{current_user.first_name} {current_user.last_name}",
        role=current_user.role.name,
        roles=current_user.role_names,
        hospital_id=current_user.hospital_id,
        is_active=current_user.is_active
    )