#!/usr/bin/env python3
"""
Frontend startup script
"""
import os
import sys
import subprocess

def main():
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(script_dir, 'frontend')
    
    # Check if frontend directory exists
    if not os.path.exists(frontend_dir):
        print("❌ Frontend directory not found!")
        sys.exit(1)
    
    # Change to frontend directory
    os.chdir(frontend_dir)
    
    # Check if package.json exists
    package_json = os.path.join(frontend_dir, 'package.json')
    if not os.path.exists(package_json):
        print("❌ package.json not found in frontend directory!")
        sys.exit(1)
    
    # Check if node_modules exists
    node_modules = os.path.join(frontend_dir, 'node_modules')
    if not os.path.exists(node_modules):
        print("📦 Installing frontend dependencies...")
        try:
            subprocess.run(['npm', 'install'], cwd=frontend_dir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            sys.exit(1)
    
    print("🌐 Starting Hospital ERP Frontend...")
    print("====================================")
    print(f"Working directory: {frontend_dir}")
    print("Starting React development server on http://localhost:3000")
    print("Press Ctrl+C to stop the server")
    print("")
    
    try:
        subprocess.run(['npm', 'start'], cwd=frontend_dir)
    except KeyboardInterrupt:
        print("\n🛑 Frontend server stopped")
    except FileNotFoundError:
        print("❌ npm not found. Please install Node.js and npm")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error starting frontend: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()