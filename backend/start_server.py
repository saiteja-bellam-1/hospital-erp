#!/usr/bin/env python3
"""
Bulletproof FastAPI server startup script
"""
import os
import sys

# Ensure we're in the right directory
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)

# Add the backend directory to Python path
sys.path.insert(0, backend_dir)

print("🏥 Starting KT HEALTH ERP Backend Server...")
print("==========================================")
print(f"Working directory: {backend_dir}")
print(f"Python path: {sys.path[0]}")

try:
    # Import and test the app first
    print("Testing imports...")
    import main
    app = main.app
    print(f"✅ FastAPI app loaded: {app.title}")
    
    # Start uvicorn programmatically
    import uvicorn
    print("Starting server on http://localhost:8000")
    print("API Documentation: http://localhost:8000/docs")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    uvicorn.run(
        "main:app",  # Use import string for reload functionality
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[backend_dir],
        log_level="info"
    )
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Make sure all dependencies are installed:")
    print("  pip install -r requirements.txt")
    sys.exit(1)
    
except Exception as e:
    print(f"❌ Error starting server: {e}")
    sys.exit(1)