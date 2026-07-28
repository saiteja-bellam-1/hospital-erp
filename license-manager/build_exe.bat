@echo off
echo ============================================
echo  KT License Manager - Build Script
echo ============================================
echo.

:: CI runs this script with stdin redirected from NUL so the trailing
:: `pause` does not block. Each step checks ERRORLEVEL and aborts on
:: failure — a failed npm/pip step must not produce a stale .exe.

echo [1/3] Building React frontend...
pushd frontend
call npm ci
if %ERRORLEVEL% neq 0 ( popd & call :FAIL_AND_EXIT "npm ci" )
call npm run build
if %ERRORLEVEL% neq 0 ( popd & call :FAIL_AND_EXIT "npm run build" )
popd
if not exist "frontend\build\index.html" (
    echo ERROR: frontend\build\index.html not found after build!
    exit /b 1
)

echo [2/3] Installing Python dependencies...
pushd backend
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 ( popd & call :FAIL_AND_EXIT "pip install -r requirements.txt" )
pip install pyinstaller
if %ERRORLEVEL% neq 0 ( popd & call :FAIL_AND_EXIT "pip install pyinstaller" )

echo [3/3] Building KTLicenseManager.exe...
pyinstaller license_manager.spec --clean --noconfirm
if %ERRORLEVEL% neq 0 ( popd & call :FAIL_AND_EXIT "pyinstaller" )
popd
if not exist "backend\dist\KTLicenseManager.exe" (
    echo ERROR: backend\dist\KTLicenseManager.exe was not created!
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Output: backend/dist/KTLicenseManager.exe
echo ============================================
pause
exit /b 0

:: `exit 1` (no /b) terminates the whole cmd.exe invocation — `exit /b 1`
:: from a call'd label would only end the subroutine and let the build
:: continue after a failure.
:FAIL_AND_EXIT
echo.
echo ============================================
echo  BUILD FAILED at step: %~1
echo ============================================
exit 1
