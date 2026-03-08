#!/usr/bin/env python3
"""
Backend startup script that ensures correct working directory and environment
"""
import os
import sys
import subprocess

def main():
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(script_dir, 'backend')
    
    # Check if backend directory exists
    if not os.path.exists(backend_dir):
        print("❌ Backend directory not found!")
        sys.exit(1)
    
    # Change to backend directory
    os.chdir(backend_dir)
    
    # Check if virtual environment exists
    venv_python = os.path.join(backend_dir, 'venv', 'bin', 'python')
    if os.name == 'nt':  # Windows
        venv_python = os.path.join(backend_dir, 'venv', 'Scripts', 'python.exe')
    
    if not os.path.exists(venv_python):
        print("❌ Virtual environment not found. Please run setup first:")
        print("   python3 install_and_setup.py")
        sys.exit(1)
    
    # Check if main.py exists
    main_py = os.path.join(backend_dir, 'main.py')
    if not os.path.exists(main_py):
        print("❌ main.py not found in backend directory!")
        sys.exit(1)
    
    print("🏥 Starting Hospital ERP Backend...")
    print("==================================")
    print(f"Working directory: {backend_dir}")
    print("Starting FastAPI server on http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the server")
    print("")
    
    # Use the bulletproof server startup script
    start_script = os.path.join(backend_dir, 'start_server.py')
    
    try:
        subprocess.run([venv_python, start_script], cwd=backend_dir)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()