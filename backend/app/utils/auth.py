from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None

def has_permission(user_permissions: list, module: str, action: str) -> bool:
    for perm in user_permissions:
        if perm.module_name == module:
            if action == "read" and perm.can_read:
                return True
            elif action == "write" and perm.can_write:
                return True
            elif action == "delete" and perm.can_delete:
                return True
            elif action == "admin" and perm.can_admin:
                return True
    return False

class UserRoles:
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"
    LAB_ADMIN = "lab_admin"
    PHARMACY_ADMIN = "pharmacy_admin"
    BILLING_ADMIN = "billing_admin"
    OUTPATIENT_ADMIN = "outpatient_admin"
    INPATIENT_ADMIN = "inpatient_admin"
    CANTEEN_ADMIN = "canteen_admin"
    CANTEEN_SALES = "canteen_sales"
    DOCTOR = "doctor"
    NURSE = "nurse"
    LAB_TECHNICIAN = "lab_technician"
    PHARMACIST = "pharmacist"
    RECEPTIONIST = "receptionist"

class Modules:
    LAB = "lab"
    PHARMACY = "pharmacy"
    BILLING = "billing"
    EHR = "ehr"
    OUTPATIENT = "outpatient"
    INPATIENT = "inpatient"
    CANTEEN = "canteen"
    ADMIN = "admin"