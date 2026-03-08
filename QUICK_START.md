# Hospital ERP - Quick Start Guide

## 🚀 Quick Setup & Run

### Step 1: Install Dependencies (One-time setup)
```bash
cd /Users/saiteja/Documents/GitHub/hospital-ERP
python3 install_and_setup.py
```

### Step 2: Start the Backend Server
**Choose ONE of these methods:**

**Method A: Direct Python Script (Recommended)**
```bash
cd backend
./venv/bin/python start_server.py
```

**Method B: Using the wrapper script**
```bash
python3 run_backend.py
```

**Method C: Shell script**
```bash
./start_backend.sh
```

### Step 3: Start the Frontend (In a new terminal)
```bash
python3 run_frontend.py
```

## 🔧 Troubleshooting

### If you get "Could not import module 'main'" error:

1. **Make sure you're in the backend directory:**
   ```bash
   cd /Users/saiteja/Documents/GitHub/hospital-ERP/backend
   ```

2. **Use the direct Python approach:**
   ```bash
   ./venv/bin/python start_server.py
   ```

3. **If port 8000 is busy:**
   ```bash
   lsof -ti:8000 | xargs kill -9
   ```

### If imports are failing:

1. **Reinstall dependencies:**
   ```bash
   cd backend
   ./venv/bin/pip install -r requirements.txt
   ```

2. **Test imports manually:**
   ```bash
   ./venv/bin/python -c "import main; print('✅ Success')"
   ```

## ✅ Success Indicators

When the backend starts correctly, you should see:
```
🏥 Starting Hospital ERP Backend Server...
==========================================
Working directory: /path/to/backend
✅ FastAPI app loaded: Hospital ERP
Starting server on http://localhost:8000
--------------------------------------------------
INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO: Started reloader process
```

## 🌐 Access Points

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000  
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## 🔑 Default Login

- **Super Admin**: `superadmin` / `admin123`
- **Hospital Admin**: `hospitaladmin` / `hospital123`

## 📞 Still Having Issues?

1. Check that Python 3.8+ and Node.js 16+ are installed
2. Ensure you're in the correct directory
3. Try the manual setup steps in README.md
4. Check for error messages in the terminal output