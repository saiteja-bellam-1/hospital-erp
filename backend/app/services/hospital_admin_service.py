import uuid
from sqlalchemy.orm import Session
from app.models.user import User, UserRole, UserPermission
from app.models.hospital import HospitalModule
from app.utils.auth import get_password_hash, UserRoles, Modules
from typing import Optional, List, Dict, Any

class HospitalAdminService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_module_admin(self, hospital_id: int, admin_data: Dict[str, Any], module_name: str) -> Optional[User]:
        # Map module names to roles
        module_role_mapping = {
            Modules.LAB: UserRoles.LAB_ADMIN,
            Modules.PHARMACY: UserRoles.PHARMACY_ADMIN,
            Modules.BILLING: UserRoles.BILLING_ADMIN,
            Modules.OUTPATIENT: UserRoles.OUTPATIENT_ADMIN,
            Modules.INPATIENT: UserRoles.INPATIENT_ADMIN
        }
        
        role_name = module_role_mapping.get(module_name)
        if not role_name:
            return None
        
        # Check if module is enabled for hospital
        hospital_module = self.db.query(HospitalModule).filter(
            HospitalModule.hospital_id == hospital_id,
            HospitalModule.module_name == module_name,
            HospitalModule.is_enabled == True
        ).first()
        
        if not hospital_module:
            return None
        
        # Get or create role
        role = self.db.query(UserRole).filter(UserRole.name == role_name).first()
        if not role:
            role = UserRole(
                name=role_name,
                description=f"{module_name.title()} Module Administrator"
            )
            self.db.add(role)
            self.db.commit()
            self.db.refresh(role)
        
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
            role_id=role.id,
            hospital_id=hospital_id
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Grant module-specific permissions
        self._grant_module_admin_permissions(user.id, module_name)
        
        return user
    
    def create_doctor(self, hospital_id: int, doctor_data: Dict[str, Any]) -> Optional[User]:
        # Get or create doctor role
        role = self.db.query(UserRole).filter(UserRole.name == UserRoles.DOCTOR).first()
        if not role:
            role = UserRole(
                name=UserRoles.DOCTOR,
                description="Doctor with access to EHR and prescription modules"
            )
            self.db.add(role)
            self.db.commit()
            self.db.refresh(role)
        
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(doctor_data["password"])
        
        user = User(
            user_id=user_id,
            username=doctor_data["username"],
            email=doctor_data["email"],
            password_hash=hashed_password,
            first_name=doctor_data["first_name"],
            last_name=doctor_data["last_name"],
            phone=doctor_data.get("phone"),
            role_id=role.id,
            hospital_id=hospital_id
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Grant doctor permissions
        self._grant_doctor_permissions(user.id)
        
        return user
    
    def create_staff_user(self, hospital_id: int, staff_data: Dict[str, Any], role_name: str) -> Optional[User]:
        # Get or create role
        role = self.db.query(UserRole).filter(UserRole.name == role_name).first()
        if not role:
            role = UserRole(
                name=role_name,
                description=f"{role_name.replace('_', ' ').title()} Role"
            )
            self.db.add(role)
            self.db.commit()
            self.db.refresh(role)
        
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(staff_data["password"])
        
        user = User(
            user_id=user_id,
            username=staff_data["username"],
            email=staff_data["email"],
            password_hash=hashed_password,
            first_name=staff_data["first_name"],
            last_name=staff_data["last_name"],
            phone=staff_data.get("phone"),
            role_id=role.id,
            hospital_id=hospital_id
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        # Grant role-specific permissions
        self._grant_staff_permissions(user.id, role_name)
        
        return user
    
    def _grant_module_admin_permissions(self, user_id: int, module_name: str):
        permission = UserPermission(
            user_id=user_id,
            module_name=module_name,
            can_read=True,
            can_write=True,
            can_delete=True,
            can_admin=True
        )
        self.db.add(permission)
        self.db.commit()
    
    def _grant_doctor_permissions(self, user_id: int):
        doctor_modules = [Modules.EHR, Modules.LAB, Modules.PHARMACY, Modules.OUTPATIENT, Modules.INPATIENT]
        
        for module in doctor_modules:
            permission = UserPermission(
                user_id=user_id,
                module_name=module,
                can_read=True,
                can_write=True,
                can_delete=False,
                can_admin=False
            )
            self.db.add(permission)
        
        self.db.commit()
    
    def _grant_staff_permissions(self, user_id: int, role_name: str):
        # Define permissions based on role
        role_permissions = {
            UserRoles.NURSE: {
                "modules": [Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT],
                "permissions": {"read": True, "write": True, "delete": False, "admin": False}
            },
            UserRoles.LAB_TECHNICIAN: {
                "modules": [Modules.LAB],
                "permissions": {"read": True, "write": True, "delete": False, "admin": False}
            },
            UserRoles.PHARMACIST: {
                "modules": [Modules.PHARMACY],
                "permissions": {"read": True, "write": True, "delete": False, "admin": False}
            },
            UserRoles.RECEPTIONIST: {
                "modules": [Modules.OUTPATIENT, Modules.BILLING],
                "permissions": {"read": True, "write": True, "delete": False, "admin": False}
            }
        }
        
        role_config = role_permissions.get(role_name)
        if role_config:
            for module in role_config["modules"]:
                permission = UserPermission(
                    user_id=user_id,
                    module_name=module,
                    can_read=role_config["permissions"]["read"],
                    can_write=role_config["permissions"]["write"],
                    can_delete=role_config["permissions"]["delete"],
                    can_admin=role_config["permissions"]["admin"]
                )
                self.db.add(permission)
        
        self.db.commit()
    
    def get_hospital_users(self, hospital_id: int) -> List[User]:
        return self.db.query(User).filter(
            User.hospital_id == hospital_id,
            User.is_active == True
        ).all()
    
    def get_users_by_role(self, hospital_id: int, role_name: str) -> List[User]:
        return self.db.query(User).join(UserRole).filter(
            User.hospital_id == hospital_id,
            User.is_active == True,
            UserRole.name == role_name
        ).all()
    
    def update_user_permissions(self, user_id: int, permissions: List[Dict[str, Any]]) -> bool:
        # Remove existing permissions
        self.db.query(UserPermission).filter(UserPermission.user_id == user_id).delete()
        
        # Add new permissions
        for perm_data in permissions:
            permission = UserPermission(
                user_id=user_id,
                module_name=perm_data["module_name"],
                can_read=perm_data.get("can_read", False),
                can_write=perm_data.get("can_write", False),
                can_delete=perm_data.get("can_delete", False),
                can_admin=perm_data.get("can_admin", False)
            )
            self.db.add(permission)
        
        self.db.commit()
        return True
    
    def deactivate_user(self, user_id: int) -> bool:
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_active = False
            self.db.commit()
            return True
        return False
    
    def get_hospital_statistics(self, hospital_id: int) -> Dict[str, Any]:
        total_users = self.db.query(User).filter(
            User.hospital_id == hospital_id,
            User.is_active == True
        ).count()
        
        # Count users by role
        role_counts = {}
        roles = self.db.query(UserRole).all()
        for role in roles:
            count = self.db.query(User).filter(
                User.hospital_id == hospital_id,
                User.is_active == True,
                User.role_id == role.id
            ).count()
            if count > 0:
                role_counts[role.name] = count
        
        # Enabled modules
        enabled_modules = self.db.query(HospitalModule).filter(
            HospitalModule.hospital_id == hospital_id,
            HospitalModule.is_enabled == True
        ).all()
        
        return {
            "total_users": total_users,
            "users_by_role": role_counts,
            "enabled_modules": [m.module_name for m in enabled_modules]
        }