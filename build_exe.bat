@echo off
echo ============================================
echo  KT HEALTH ERP - Windows Build Script
echo ============================================
echo.

:: Step 1: Clean old build artifacts
echo [1/4] Cleaning old build artifacts...
if exist "frontend\build" (
    rmdir /s /q "frontend\build"
    echo   - Removed old frontend\build
)
if exist "backend\build" (
    rmdir /s /q "backend\build"
    echo   - Removed old backend\build
)
if exist "backend\dist" (
    rmdir /s /q "backend\dist"
    echo   - Removed old backend\dist
)
echo Clean complete.
echo.

:: Step 2: Build React frontend
echo [2/4] Building React frontend...
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

:: Verify frontend build exists
if not exist "frontend\build\index.html" (
    echo ERROR: frontend\build\index.html not found after build!
    pause
    exit /b 1
)
echo Frontend build complete.
echo.

:: Step 3: Install Python dependencies
echo [3/4] Installing Python dependencies...
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

:: Step 4: Build exe with PyInstaller
echo [4/4] Building KTHEALTHERP.exe...
pyinstaller hospital_erp.spec --clean --noconfirm
if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)
cd ..

:: Verify output
if not exist "backend\dist\KTHEALTHERP.exe" (
    echo ERROR: KTHEALTHERP.exe was not created!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Output: backend\dist\KTHEALTHERP.exe
echo ============================================
echo.
echo IMPORTANT: Always use this script to build.
echo Running PyInstaller directly will bundle the
echo OLD frontend and your UI changes won't appear.
echo.
echo To run: copy KTHEALTHERP.exe to any folder and double-click it.
echo The app will create a data\ folder for the database and uploads.
echo.
pause
