import string
import random
from sqlalchemy.orm import Session
from app.models.hospital import Hospital, HospitalModule
from app.models.user import User, UserRole, UserPermission
from app.utils.auth import get_password_hash, UserRoles, Modules
from typing import Optional, List, Dict, Any
import json


def generate_hospital_code(length=6):
    """Generate a 6-char alphanumeric hospital code like 'K7X2M9'."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))

class SuperAdminService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_hospital(self, hospital_data: Dict[str, Any]) -> Hospital:
        # Generate unique 6-char alphanumeric code
        while True:
            hospital_id = generate_hospital_code()
            existing = self.db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()
            if not existing:
                break

        hospital = Hospital(
            hospital_id=hospital_id,
            name=hospital_data["name"],
            address=hospital_data.get("address"),
            phone=hospital_data.get("phone"),
            email=hospital_data.get("email"),
            license_number=hospital_data.get("license_number")
        )
        
        self.db.add(hospital)
        self.db.commit()
        self.db.refresh(hospital)
        
        # Initialize default modules for hospital
        self._initialize_hospital_modules(hospital.id)
        
        return hospital
    
    def _initialize_hospital_modules(self, hospital_id: int):
        default_modules = [
            Modules.LAB, Modules.PHARMACY, Modules.BILLING,
            Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT
        ]
        
        for module_name in default_modules:
            hospital_module = HospitalModule(
                hospital_id=hospital_id,
                module_name=module_name,
                is_enabled=False,
                configuration=json.dumps({})
            )
            self.db.add(hospital_module)
        
        self.db.commit()
    
    def get_all_hospitals(self) -> List[Hospital]:
        return self.db.query(Hospital).filter(Hospital.is_active == True).all()
    
    def get_hospital_by_id(self, hospital_id: str) -> Optional[Hospital]:
        return self.db.query(Hospital).filter(
            Hospital.hospital_id == hospital_id,
            Hospital.is_active == True
        ).first()
    
    def update_hospital(self, hospital_id: str, update_data: Dict[str, Any]) -> Optional[Hospital]:
        hospital = self.get_hospital_by_id(hospital_id)
        if not hospital:
            return None
        
        for key, value in update_data.items():
            if hasattr(hospital, key):
                setattr(hospital, key, value)
        
        self.db.commit()
        self.db.refresh(hospital)
        return hospital
    
    def enable_module_for_hospital(self, hospital_id: str, module_name: str, configuration: Dict[str, Any] = None) -> bool:
        hospital = self.get_hospital_by_id(hospital_id)
        if not hospital:
            return False
        
        hospital_module = self.db.query(HospitalModule).filter(
            HospitalModule.hospital_id == hospital.id,
            HospitalModule.module_name == module_name
        ).first()
        
        if hospital_module:
            hospital_module.is_enabled = True
            if configuration:
                hospital_module.configuration = json.dumps(configuration)
            self.db.commit()
            return True
        
        return False
    
    def disable_module_for_hospital(self, hospital_id: str, module_name: str) -> bool:
        hospital = self.get_hospital_by_id(hospital_id)
        if not hospital:
            return False
        
        hospital_module = self.db.query(HospitalModule).filter(
            HospitalModule.hospital_id == hospital.id,
            HospitalModule.module_name == module_name
        ).first()
        
        if hospital_module:
            hospital_module.is_enabled = False
            self.db.commit()
            return True
        
        return False
    
    def get_hospital_modules(self, hospital_id: str) -> List[HospitalModule]:
        hospital = self.get_hospital_by_id(hospital_id)
        if not hospital:
            return []
        
        return self.db.query(HospitalModule).filter(
            HospitalModule.hospital_id == hospital.id
        ).all()
    
    def create_hospital_admin(self, hospital_id: str, admin_data: Dict[str, Any]) -> Optional[User]:
        hospital = self.get_hospital_by_id(hospital_id)
        if not hospital:
            return None
        
        # Check if hospital admin role exists
        admin_role = self.db.query(UserRole).filter(
            UserRole.name == UserRoles.HOSPITAL_ADMIN
        ).first()
        
        if not admin_role:
            admin_role = UserRole(
                name=UserRoles.HOSPITAL_ADMIN,
                description="Hospital Administrator with access to all hospital modules"
            )
            self.db.add(admin_role)
            self.db.commit()
            self.db.refresh(admin_role)
        
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(admin_data["password"])
        
        user = User(
            user_id=user_id,
            username=admin_data["username"],
            email=admin_data["email"],
            password_hash=hashed_password,
            first_name=admin_data["first_name"],
            last_name=admin_data["last_name"],
            phone=admin_data.get("phone"),
            role_id=admin_role.id,
            hospital_id=hospital.id
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Grant all module permissions to hospital admin
        self._grant_hospital_admin_permissions(user.id)
        
        return user
    
    def _grant_hospital_admin_permissions(self, user_id: int):
        modules = [
            Modules.LAB, Modules.PHARMACY, Modules.BILLING,
            Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT, Modules.ADMIN
        ]
        
        for module in modules:
            permission = UserPermission(
                user_id=user_id,
                module_name=module,
                can_read=True,
                can_write=True,
                can_delete=True,
                can_admin=True
            )
            self.db.add(permission)
        
        self.db.commit()
    
    def get_system_statistics(self) -> Dict[str, Any]:
        total_hospitals = self.db.query(Hospital).filter(Hospital.is_active == True).count()
        total_users = self.db.query(User).filter(User.is_active == True).count()
        
        # Module usage statistics
        module_stats = {}
        for module in [Modules.LAB, Modules.PHARMACY, Modules.BILLING, Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT]:
            enabled_count = self.db.query(HospitalModule).filter(
                HospitalModule.module_name == module,
                HospitalModule.is_enabled == True
            ).count()
            module_stats[module] = enabled_count
        
        return {
            "total_hospitals": total_hospitals,
            "total_users": total_users,
            "module_usage": module_stats
        }