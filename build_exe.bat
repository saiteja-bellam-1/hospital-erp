@echo off
echo ============================================
echo  Hospital ERP - Windows Build Script
echo ============================================
echo.

:: Step 1: Build React frontend
echo [1/3] Building React frontend...
cd frontend
call npm ci
if %ERRORLEVEL% neq 0 (
    echo ERROR: npm ci failed
    pause
    exit /b 1
)
call npm run build
if %ERRORLEVEL% neq 0 (
    echo ERROR: npm run build failed
    pause
    exit /b 1
)
cd ..
echo Frontend build complete.
echo.

:: Step 2: Install Python dependencies
echo [2/3] Installing Python dependencies...
cd backend
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
pip install pyinstaller
if %ERRORLEVEL% neq 0 (
    echo ERROR: pyinstaller install failed
    pause
    exit /b 1
)
echo Dependencies installed.
echo.

:: Step 3: Build exe with PyInstaller
echo [3/3] Building HospitalERP.exe...
pyinstaller hospital_erp.spec --clean --noconfirm
if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)
cd ..

echo.
echo ============================================
echo  Build complete!
echo  Output: backend\dist\HospitalERP.exe
echo ============================================
echo.
echo To run: copy HospitalERP.exe to any folder and double-click it.
echo The app will create a data\ folder for the database and uploads.
echo.
pause
