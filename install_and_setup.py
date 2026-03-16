#!/usr/bin/env python3
"""
Complete installation and setup script for KT HEALTH ERP
Handles virtual environment creation, dependency installation, and database setup
"""

import subprocess
import sys
import os
import platform

def run_command(command, cwd=None, check=True):
    """Run a command and handle errors"""
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=True, check=check, cwd=cwd, 
                              capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error output: {e.stderr}")
        if check:
            sys.exit(1)
        return e

def main():
    print("🏥 KT HEALTH ERP Installation Script")
    print("=" * 50)
    
    # Get current directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(project_dir, 'backend')
    frontend_dir = os.path.join(project_dir, 'frontend')
    
    # Check Python version
    python_version = sys.version_info
    if python_version < (3, 8):
        print("❌ Python 3.8+ is required")
        sys.exit(1)
    print(f"✅ Python {python_version.major}.{python_version.minor} detected")
    
    # Backend Setup
    print("\n📦 Setting up Backend...")
    
    # Create virtual environment
    venv_path = os.path.join(backend_dir, 'venv')
    if not os.path.exists(venv_path):
        print("Creating virtual environment...")
        run_command(f"{sys.executable} -m venv venv", cwd=backend_dir)
    else:
        print("✅ Virtual environment already exists")
    
    # Determine activation script path based on OS
    if platform.system() == "Windows":
        activate_script = os.path.join(venv_path, 'Scripts', 'activate')
        python_executable = os.path.join(venv_path, 'Scripts', 'python')
        pip_executable = os.path.join(venv_path, 'Scripts', 'pip')
    else:
        activate_script = os.path.join(venv_path, 'bin', 'activate')
        python_executable = os.path.join(venv_path, 'bin', 'python')
        pip_executable = os.path.join(venv_path, 'bin', 'pip')
    
    # Install Python dependencies
    print("Installing Python dependencies...")
    run_command(f"{pip_executable} install --upgrade pip", cwd=backend_dir)
    run_command(f"{pip_executable} install -r requirements.txt", cwd=backend_dir)
    
    print("✅ Backend dependencies installed")
    
    # Frontend Setup
    print("\n🌐 Setting up Frontend...")
    
    # Check if Node.js is installed
    try:
        result = run_command("node --version", check=False)
        if result.returncode == 0:
            print(f"✅ Node.js detected: {result.stdout.strip()}")
        else:
            print("❌ Node.js not found. Please install Node.js 16+ and npm")
            print("Download from: https://nodejs.org/")
            sys.exit(1)
    except:
        print("❌ Node.js not found. Please install Node.js 16+ and npm")
        sys.exit(1)
    
    # Install npm dependencies
    if os.path.exists(os.path.join(frontend_dir, 'package.json')):
        print("Installing npm dependencies...")
        run_command("npm install", cwd=frontend_dir)
        print("✅ Frontend dependencies installed")
    else:
        print("❌ Frontend package.json not found")
        sys.exit(1)
    
    # Database Setup
    print("\n🗄️ Setting up Database...")
    
    # Run the database setup script using the virtual environment Python
    setup_script = os.path.join(project_dir, 'setup_database.py')
    
    # Create a simplified database setup script
    setup_script_content = f'''#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, r"{project_dir}")
sys.path.insert(0, r"{backend_dir}")

from sqlalchemy.orm import Session
from backend.config.database import SessionLocal, create_tables
from backend.app.models.user import UserRole, User
from backend.app.models.hospital import Hospital, HospitalModule
from backend.app.utils.auth import get_password_hash, UserRoles, Modules
import uuid
import json

def create_default_roles(db: Session):
    roles = [
        (UserRoles.SUPER_ADMIN, "Super Administrator with system-wide access"),
        (UserRoles.HOSPITAL_ADMIN, "Hospital Administrator with full hospital access"),
        (UserRoles.LAB_ADMIN, "Laboratory Module Administrator"),
        (UserRoles.PHARMACY_ADMIN, "Pharmacy Module Administrator"),
        (UserRoles.BILLING_ADMIN, "Billing Module Administrator"),
        (UserRoles.OUTPATIENT_ADMIN, "Outpatient Module Administrator"),
        (UserRoles.INPATIENT_ADMIN, "Inpatient Module Administrator"),
        (UserRoles.DOCTOR, "Doctor with EHR access"),
        (UserRoles.NURSE, "Nurse with patient care access"),
        (UserRoles.LAB_TECHNICIAN, "Lab Technician"),
        (UserRoles.PHARMACIST, "Pharmacist"),
        (UserRoles.RECEPTIONIST, "Receptionist"),
    ]
    
    for role_name, description in roles:
        existing_role = db.query(UserRole).filter(UserRole.name == role_name).first()
        if not existing_role:
            role = UserRole(name=role_name, description=description)
            db.add(role)
    db.commit()
    print("✓ Default roles created")

def create_super_admin(db: Session):
    super_admin_role = db.query(UserRole).filter(UserRole.name == UserRoles.SUPER_ADMIN).first()
    existing_admin = db.query(User).filter(User.username == "superadmin").first()
    if not existing_admin:
        admin_user = User(
            user_id=str(uuid.uuid4()),
            username="superadmin",
            email="admin@kthealth-erp.local",
            password_hash=get_password_hash("admin123"),
            first_name="Super",
            last_name="Admin",
            phone="1234567890",
            role_id=super_admin_role.id,
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        print("✓ Super admin created")
    else:
        print("✓ Super admin already exists")

def create_demo_hospital(db: Session):
    existing_hospital = db.query(Hospital).filter(Hospital.name == "Demo Hospital").first()
    if not existing_hospital:
        hospital = Hospital(
            hospital_id=str(uuid.uuid4()),
            name="Demo Hospital",
            address="123 Medical Center Drive, Healthcare City, HC 12345",
            phone="555-HOSPITAL",
            email="info@demohospital.local",
            license_number="DEMO-HOSPITAL-001"
        )
        db.add(hospital)
        db.commit()
        db.refresh(hospital)
        
        modules = [Modules.LAB, Modules.PHARMACY, Modules.BILLING, 
                  Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT]
        
        for module_name in modules:
            hospital_module = HospitalModule(
                hospital_id=hospital.id,
                module_name=module_name,
                is_enabled=True,
                configuration=json.dumps({{}})
            )
            db.add(hospital_module)
        db.commit()
        print("✓ Demo hospital created")
        
        # Create hospital admin
        hospital_admin_role = db.query(UserRole).filter(UserRole.name == UserRoles.HOSPITAL_ADMIN).first()
        existing_admin = db.query(User).filter(User.username == "hospitaladmin").first()
        if not existing_admin:
            admin_user = User(
                user_id=str(uuid.uuid4()),
                username="hospitaladmin",
                email="admin@demohospital.local",
                password_hash=get_password_hash("hospital123"),
                first_name="Hospital",
                last_name="Admin",
                phone="555-ADMIN",
                role_id=hospital_admin_role.id,
                hospital_id=hospital.id,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("✓ Hospital admin created")

def main():
    try:
        create_tables()
        print("✓ Database tables created")
        
        db = SessionLocal()
        create_default_roles(db)
        create_super_admin(db)
        create_demo_hospital(db)
        db.close()
        
        print("\\n✅ Database setup complete!")
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {{e}}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    # Write and run the setup script
    with open(setup_script, 'w') as f:
        f.write(setup_script_content)
    
    # Run the database setup
    result = run_command(f"{python_executable} {setup_script}", cwd=project_dir, check=False)
    
    if result.returncode == 0:
        print("✅ Database initialized successfully")
    else:
        print("❌ Database initialization failed")
        print("Error:", result.stderr)
        sys.exit(1)
    
    # Clean up temporary script
    if os.path.exists(setup_script):
        os.remove(setup_script)
    
    # Final instructions
    print("\n" + "=" * 60)
    print("🎉 KT HEALTH ERP Setup Complete!")
    print("=" * 60)
    print("Default Login Credentials:")
    print("-" * 30)
    print("Super Admin:")
    print("  Username: superadmin")
    print("  Password: admin123")
    print()
    print("Hospital Admin (Demo Hospital):")
    print("  Username: hospitaladmin")
    print("  Password: hospital123")
    print()
    print("To start the application:")
    print("-" * 30)
    print("1. Backend (Terminal 1):")
    print(f"   cd {backend_dir}")
    if platform.system() == "Windows":
        print("   .\\venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("   uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    print()
    print("2. Frontend (Terminal 2):")
    print(f"   cd {frontend_dir}")
    print("   npm start")
    print()
    print("Application URLs:")
    print("  Frontend: http://localhost:3000")
    print("  Backend API: http://localhost:8000")
    print("  API Docs: http://localhost:8000/docs")
    print("=" * 60)

if __name__ == "__main__":
    main()