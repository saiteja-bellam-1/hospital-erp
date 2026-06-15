from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from config.database import get_db
from app.models.user import User, UserRole, UserPermission
from app.utils.auth import verify_token, has_permission, UserRoles, Modules

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def _user_has_any_role(user: User, role_names: list) -> bool:
    """Check if user has ANY of the given roles (checks both primary and multi-role)."""
    user_roles = set(user.role_names)
    return bool(user_roles & set(role_names))


def require_permission(module: str, action: str):
    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        user_roles = set(current_user.role_names)

        if UserRoles.SUPER_ADMIN in user_roles:
            return current_user

        if UserRoles.HOSPITAL_ADMIN in user_roles:
            return current_user

        # Lab roles always have access to lab module
        if module == Modules.LAB and user_roles & {UserRoles.LAB_ADMIN, UserRoles.LAB_TECHNICIAN}:
            return current_user

        # Check if module is enabled in system settings
        from app.models.system import SystemModule
        sys_module = db.query(SystemModule).filter(
            SystemModule.module_name == module
        ).first()
        if sys_module and not sys_module.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module}' is not enabled"
            )

        # Check if module is covered by the license
        from app.services.license_service import get_current_license
        license_record = get_current_license(db)
        if license_record and license_record.features:
            if module not in license_record.features:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Module '{module}' is not included in your license"
                )

        # Import here to avoid circular imports
        from app.models.permissions import RoleModulePermission

        # Check role-based permissions for ALL of the user's roles
        for r in (current_user.roles or []):
            role_permissions = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == r.id,
                RoleModulePermission.module_name == module
            ).first()

            if role_permissions and role_permissions.permissions:
                action_mapping = {
                    'read': ['view_appointments', 'view_patients', 'view_schedules', 'read',
                             'view_reports', 'view_records', 'view_history', 'view_prescriptions',
                             'view_occupancy', 'view_financial_reports', 'view_system_reports',
                             'view_vitals', 'view_mar'],
                    'write': ['schedule_appointments', 'register_patients', 'manage_queues', 'write',
                              'update_appointments', 'create_reports', 'edit_records', 'create_prescriptions',
                              'process_payments', 'generate_invoices', 'dispense_medications',
                              'admit_patients', 'discharge_patients', 'manage_tests', 'set_rates',
                              'manage_inventory', 'manage_templates', 'manage_equipment', 'generate_reports',
                              'record_vitals', 'administer_medications', 'manage_nursing_notes',
                              'manage_allergies'],
                    'delete': ['cancel_appointments', 'schedule_appointments', 'delete',
                               'handle_refunds', 'manage_tests', 'manage_inventory'],
                    'admin': ['manage_schedules', 'admin', 'manage_users', 'manage_roles',
                              'manage_modules', 'manage_settings', 'manage_suppliers',
                              'manage_insurance', 'manage_beds', 'manage_wards', 'set_room_rates']
                }

                required_perms = action_mapping.get(action, [action])
                for perm in required_perms:
                    if perm in role_permissions.permissions:
                        return current_user

        # Also check primary role_id permissions (backward compat)
        from app.models.permissions import RoleModulePermission
        role_permissions = db.query(RoleModulePermission).filter(
            RoleModulePermission.role_id == current_user.role_id,
            RoleModulePermission.module_name == module
        ).first()
        if role_permissions and role_permissions.permissions:
            action_mapping = {
                'read': ['view_appointments', 'view_patients', 'view_schedules', 'read',
                         'view_reports', 'view_records', 'view_history', 'view_prescriptions',
                         'view_occupancy', 'view_financial_reports', 'view_system_reports'],
                'write': ['schedule_appointments', 'register_patients', 'manage_queues', 'write',
                          'update_appointments', 'create_reports', 'edit_records', 'create_prescriptions',
                          'process_payments', 'generate_invoices', 'dispense_medications',
                          'admit_patients', 'discharge_patients', 'manage_tests', 'set_rates',
                          'manage_inventory', 'manage_templates', 'manage_equipment', 'generate_reports'],
                'delete': ['cancel_appointments', 'schedule_appointments', 'delete',
                           'handle_refunds', 'manage_tests', 'manage_inventory'],
                'admin': ['manage_schedules', 'admin', 'manage_users', 'manage_roles',
                          'manage_modules', 'manage_settings', 'manage_suppliers',
                          'manage_insurance', 'manage_beds', 'manage_wards', 'set_room_rates']
            }
            required_perms = action_mapping.get(action, [action])
            for perm in required_perms:
                if perm in role_permissions.permissions:
                    return current_user

        # Fallback to user-specific permissions
        user_permissions = db.query(UserPermission).filter(
            UserPermission.user_id == current_user.id
        ).all()

        if not has_permission(user_permissions, module, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {action} on {module}"
            )

        return current_user

    return permission_checker

def require_feature_permission(module: str, permission_name: str):
    """Require a specific permission key on the given module (fine-grained auth).

    Unlike `require_permission(module, action)` which matches any permission in
    an action bucket, this checks for one specific permission name. Super_admin
    and hospital_admin bypass. Module-enabled and license gates still apply."""
    def feature_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        user_roles = set(current_user.role_names)

        if UserRoles.SUPER_ADMIN in user_roles:
            return current_user
        if UserRoles.HOSPITAL_ADMIN in user_roles:
            return current_user

        # Module-enabled check
        from app.models.system import SystemModule
        sys_module = db.query(SystemModule).filter(
            SystemModule.module_name == module
        ).first()
        if sys_module and not sys_module.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module}' is not enabled",
            )

        # License feature gate
        from app.services.license_service import get_current_license
        license_record = get_current_license(db)
        if license_record and license_record.features:
            if module not in license_record.features:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Module '{module}' is not included in your license",
                )

        from app.models.permissions import RoleModulePermission

        # Collect all role ids the user has (multi-role + legacy primary role_id)
        role_ids = [r.id for r in (current_user.roles or [])]
        if current_user.role_id and current_user.role_id not in role_ids:
            role_ids.append(current_user.role_id)

        for rid in role_ids:
            rp = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == rid,
                RoleModulePermission.module_name == module,
            ).first()
            if rp and rp.permissions and permission_name in rp.permissions:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{permission_name}' required on {module}",
        )
    return feature_checker


def user_has_feature_permission(
    db: Session,
    current_user: User,
    module: str,
    permission_name: str,
) -> bool:
    """Return True if the user holds a specific module permission (admins bypass)."""
    user_roles = set(current_user.role_names)
    if UserRoles.SUPER_ADMIN in user_roles or UserRoles.HOSPITAL_ADMIN in user_roles:
        return True

    from app.models.system import SystemModule
    sys_module = db.query(SystemModule).filter(
        SystemModule.module_name == module
    ).first()
    if sys_module and not sys_module.is_enabled:
        return False

    from app.services.license_service import get_current_license
    license_record = get_current_license(db)
    if license_record and license_record.features:
        if module not in license_record.features:
            return False

    from app.models.permissions import RoleModulePermission

    role_ids = [r.id for r in (current_user.roles or [])]
    if current_user.role_id and current_user.role_id not in role_ids:
        role_ids.append(current_user.role_id)

    for rid in role_ids:
        rp = db.query(RoleModulePermission).filter(
            RoleModulePermission.role_id == rid,
            RoleModulePermission.module_name == module,
        ).first()
        if rp and rp.permissions and permission_name in rp.permissions:
            return True
    return False


def require_feature_permission_any(module: str, *permission_names: str):
    """Require at least one of the listed permission keys on the module."""
    names = tuple(permission_names)
    if not names:
        raise ValueError("require_feature_permission_any needs at least one permission")

    def feature_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        user_roles = set(current_user.role_names)
        if UserRoles.SUPER_ADMIN in user_roles or UserRoles.HOSPITAL_ADMIN in user_roles:
            return current_user

        from app.models.system import SystemModule
        sys_module = db.query(SystemModule).filter(
            SystemModule.module_name == module
        ).first()
        if sys_module and not sys_module.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Module '{module}' is not enabled",
            )

        from app.services.license_service import get_current_license
        license_record = get_current_license(db)
        if license_record and license_record.features:
            if module not in license_record.features:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Module '{module}' is not included in your license",
                )

        for permission_name in names:
            if user_has_feature_permission(db, current_user, module, permission_name):
                return current_user

        joined = "', '".join(names)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"One of '{joined}' required on {module}",
        )

    return feature_checker


def require_role(required_roles: list):
    def role_checker(current_user: User = Depends(get_current_user)):
        if not _user_has_any_role(current_user, required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions"
            )
        return current_user

    return role_checker

def require_super_admin(current_user: User = Depends(get_current_user)):
    if not current_user.has_role(UserRoles.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user

def require_hospital_admin_or_above(current_user: User = Depends(get_current_user)):
    if not _user_has_any_role(current_user, [UserRoles.SUPER_ADMIN, UserRoles.HOSPITAL_ADMIN]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital admin or super admin access required"
        )
    return current_user
