#!/usr/bin/env python3

"""
Script to consolidate receptionist and frontdesk roles
- Both roles have the same function: patient registration and appointment booking
- Migrate all frontdesk users to receptionist role
- Remove frontdesk role and permissions
- Update role description for receptionist
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import SessionLocal, create_tables
from app.models.user import User, UserRole
from app.models.permissions import RoleModulePermission

def consolidate_roles():
    db = SessionLocal()
    
    try:
        print("🔄 Starting role consolidation...")
        
        # Find receptionist and frontdesk roles
        receptionist_role = db.query(UserRole).filter(UserRole.name == 'receptionist').first()
        frontdesk_role = db.query(UserRole).filter(UserRole.name == 'frontdesk').first()
        
        if not receptionist_role:
            print("❌ Receptionist role not found!")
            return
            
        if not frontdesk_role:
            print("ℹ️  Frontdesk role not found, nothing to consolidate")
            return
            
        print(f"📋 Found receptionist role (ID: {receptionist_role.id})")
        print(f"📋 Found frontdesk role (ID: {frontdesk_role.id})")
        
        # Find all users with frontdesk role
        frontdesk_users = db.query(User).filter(User.role_id == frontdesk_role.id).all()
        print(f"👥 Found {len(frontdesk_users)} frontdesk users to migrate")
        
        # Migrate frontdesk users to receptionist FIRST
        for user in frontdesk_users:
            print(f"   Migrating user: {user.username} ({user.email})")
            user.role_id = receptionist_role.id
        
        # Commit user migrations first
        db.commit()
        print(f"✅ Successfully migrated {len(frontdesk_users)} users to receptionist role")
        
        # Update receptionist role description to include both functions
        receptionist_role.description = "Reception and Front Desk Staff - manages patient registration, appointment scheduling, and front desk operations"
        
        # Remove frontdesk permissions (receptionist already has the same ones)
        frontdesk_permissions = db.query(RoleModulePermission).filter(RoleModulePermission.role_id == frontdesk_role.id).all()
        for perm in frontdesk_permissions:
            print(f"   Removing frontdesk permission for module: {perm.module_name}")
            db.delete(perm)
        
        # Remove frontdesk role
        print(f"🗑️  Removing frontdesk role")
        db.delete(frontdesk_role)
        
        # Commit remaining changes
        db.commit()
        print("✅ Role consolidation completed successfully!")
        print(f"✅ {len(frontdesk_users)} users migrated from frontdesk to receptionist")
        print("✅ Frontdesk role and permissions removed")
        
        # Show final receptionist users
        all_receptionists = db.query(User).filter(User.role_id == receptionist_role.id).all()
        print(f"\n📊 Total receptionist users after consolidation: {len(all_receptionists)}")
        for user in all_receptionists:
            print(f"   - {user.username} ({user.first_name} {user.last_name})")
            
    except Exception as e:
        print(f"❌ Error during role consolidation: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    consolidate_roles()