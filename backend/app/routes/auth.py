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
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

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

    # Check inactive separately so we can give a specific message,
    # but keep "not found" and "wrong password" identical to prevent username enumeration.
    if user and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your account has been disabled. Please contact your administrator."
        )

    if not user:
        # Log failed attempt for non-existent user
        try:
            from app.services.audit_service import log_action
            log_action(db, None, "login_failed", "auth", "User", None,
                       f"Failed login attempt for unknown username: {user_credentials.username}")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Verify password
    if not verify_password(user_credentials.password, user.password_hash):
        # Log failed attempt
        try:
            from app.services.audit_service import log_action
            log_action(db, user, "login_failed", "auth", "User", user.id,
                       f"Failed login attempt for user: {user.username} (wrong password)")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
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
        is_active=user.is_active,
        must_change_password=bool(getattr(user, "must_change_password", False)),
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
        is_active=current_user.is_active,
        must_change_password=bool(getattr(current_user, "must_change_password", False)),
    )


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated password change. Clears the must_change_password flag.

    Used both for the forced first-login change and for any user updating
    their own password later.
    """
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    db.commit()

    try:
        from app.services.audit_service import log_action
        log_action(db, current_user, "change_password", "auth", "User", current_user.id,
                   f"{current_user.username} changed their own password")
    except Exception:
        pass

    return {"success": True, "message": "Password updated"}