@echo off
echo ============================================
echo  KT License Manager - Build Script
echo ============================================
echo.

echo [1/3] Building React frontend...
cd frontend
call npm ci
call npm run build
cd ..

echo [2/3] Installing Python dependencies...
cd backend
pip install -r requirements.txt
pip install pyinstaller

echo [3/3] Building KTLicenseManager.exe...
pyinstaller license_manager.spec --clean --noconfirm
cd ..

echo.
echo ============================================
echo  Build complete!
echo  Output: backend/dist/KTLicenseManager.exe
echo ============================================
pause
