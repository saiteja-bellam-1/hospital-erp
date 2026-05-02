#!/usr/bin/env python3
"""
KT HEALTH ERP — environment installer.

Sets up the Python virtualenv and installs backend + frontend dependencies.

It does NOT create any database, hospital, or admin user. The very first time
the backend is launched, the browser opens the Setup Wizard which is the only
path that creates the admin account (with the password the operator chooses).
This avoids shipping any default credentials.
"""

import subprocess
import sys
import os
import platform


def run_command(command, cwd=None, check=True):
    print(f"Running: {command}")
    try:
        result = subprocess.run(
            command, shell=True, check=check, cwd=cwd,
            capture_output=True, text=True,
        )
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
    print("KT HEALTH ERP Installation")
    print("=" * 50)

    project_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(project_dir, 'backend')
    frontend_dir = os.path.join(project_dir, 'frontend')

    if sys.version_info < (3, 8):
        print("Python 3.8+ is required")
        sys.exit(1)
    print(f"Python {sys.version_info.major}.{sys.version_info.minor} detected")

    print("\nSetting up backend...")
    venv_path = os.path.join(backend_dir, 'venv')
    if not os.path.exists(venv_path):
        print("Creating virtual environment...")
        run_command(f"{sys.executable} -m venv venv", cwd=backend_dir)
    else:
        print("Virtual environment already exists")

    if platform.system() == "Windows":
        python_executable = os.path.join(venv_path, 'Scripts', 'python')
        pip_executable = os.path.join(venv_path, 'Scripts', 'pip')
    else:
        python_executable = os.path.join(venv_path, 'bin', 'python')
        pip_executable = os.path.join(venv_path, 'bin', 'pip')

    print("Installing Python dependencies...")
    run_command(f"{pip_executable} install --upgrade pip", cwd=backend_dir)
    # Prefer the pinned lockfile for reproducible installs; fall back to
    # requirements.txt if it isn't present (e.g. fresh checkout, lock not
    # generated yet).
    lockfile = os.path.join(backend_dir, 'requirements.lock')
    if os.path.isfile(lockfile):
        print("Using pinned requirements.lock")
        run_command(f"{pip_executable} install -r requirements.lock", cwd=backend_dir)
    else:
        print("requirements.lock not found — falling back to requirements.txt")
        run_command(f"{pip_executable} install -r requirements.txt", cwd=backend_dir)
    print("Backend dependencies installed")

    print("\nSetting up frontend...")
    node_check = run_command("node --version", check=False)
    if node_check.returncode != 0:
        print("Node.js not found. Please install Node.js 16+ and npm")
        print("Download from: https://nodejs.org/")
        sys.exit(1)
    print(f"Node.js detected: {node_check.stdout.strip()}")

    if not os.path.exists(os.path.join(frontend_dir, 'package.json')):
        print("Frontend package.json not found")
        sys.exit(1)
    print("Installing npm dependencies...")
    run_command("npm install", cwd=frontend_dir)
    print("Frontend dependencies installed")

    print("\n" + "=" * 60)
    print("Installation complete.")
    print("=" * 60)
    print("\nNo admin account has been created yet — the Setup Wizard will")
    print("prompt for your hospital info and admin credentials the first")
    print("time you open the app in a browser.")
    print("\nTo start the application:\n")
    print("1. Backend (Terminal 1):")
    print(f"   cd {backend_dir}")
    if platform.system() == "Windows":
        print("   .\\venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    print("   uvicorn main:app --host 0.0.0.0 --port 8000 --reload\n")
    print("2. Frontend (Terminal 2):")
    print(f"   cd {frontend_dir}")
    print("   npm start\n")
    print("Then open http://localhost:3000 to run the Setup Wizard.")
    print("=" * 60)


if __name__ == "__main__":
    main()
