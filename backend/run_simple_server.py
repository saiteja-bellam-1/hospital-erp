#!/usr/bin/env python3
"""
Simple server startup without reload conflicts
"""
import os
import sys

# Ensure correct directory and paths
backend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

print("🏥 Hospital ERP Backend Server")
print("==============================")
print(f"Directory: {backend_dir}")

try:
    # Import and run
    import uvicorn
    print("✅ Starting server on http://localhost:8000")
    print("✅ API docs at http://localhost:8000/docs")
    print("✅ Press Ctrl+C to stop")
    print("")
    
    # Run without reload to avoid conflicts
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8000,
        log_level="info"
    )
    
except Exception as e:
    print(f"❌ Server error: {e}")
    import traceback
    traceback.print_exc()