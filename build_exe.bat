@echo off
setlocal EnableDelayedExpansion
echo ============================================
echo  KT HEALTH ERP - Windows Build Script
echo ============================================
echo.

:: ---------------------------------------------------------------
:: Build logs go in build_logs\ — one file per step. On failure
:: we tail the last 50 lines of the offending log so the user can
:: see what went wrong without scrolling thousands of lines.
::
:: Optional code signing (item 15 of installer overhaul):
::   set SIGNING_CERT=path\to\cert.pfx
::   set SIGNING_PASS=your-password
::   set SIGNING_TIMESTAMP=http://timestamp.digicert.com
:: signtool.exe must be on PATH (ships with Windows SDK).
:: If SIGNING_CERT is not set, the signing step is skipped silently.
:: ---------------------------------------------------------------

if not exist "build_logs" mkdir "build_logs"
:: wmic was removed from Windows 11 / Server 2025. Use PowerShell for the
:: timestamp instead — works on every supported Windows version.
for /f "usebackq tokens=*" %%I in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set TS=%%I
set LOG_DIR=build_logs\!TS!
mkdir "!LOG_DIR!" 2>nul
echo Build logs: !LOG_DIR!\
echo.

:: ---------- Step 1: Clean ----------
echo [1/5] Cleaning old build artifacts...
if exist "frontend\build" rmdir /s /q "frontend\build"
if exist "backend\build"  rmdir /s /q "backend\build"
if exist "backend\dist"   rmdir /s /q "backend\dist"
echo Clean complete.
echo.

:: ---------- Step 2: React build ----------
echo [2/5] Building React frontend...
pushd frontend
call npm ci > "..\!LOG_DIR!\02a_npm_ci.log" 2>&1
if %ERRORLEVEL% neq 0 ( popd & call :FAIL "npm ci" "!LOG_DIR!\02a_npm_ci.log" )
call npm run build > "..\!LOG_DIR!\02b_npm_build.log" 2>&1
if %ERRORLEVEL% neq 0 ( popd & call :FAIL "npm run build" "!LOG_DIR!\02b_npm_build.log" )
popd
if not exist "frontend\build\index.html" (
    echo ERROR: frontend\build\index.html not found after build!
    pause & exit /b 1
)
echo Frontend build complete.
echo.

:: ---------- Step 3: Python deps ----------
echo [3/5] Installing Python dependencies...
pushd backend
:: Prefer the pinned lockfile if present — gives reproducible builds across
:: machines / dates. Fall back to requirements.txt for first-time installs.
if exist "requirements.lock" (
    echo   Using pinned requirements.lock
    pip install -r requirements.lock > "..\!LOG_DIR!\03a_pip_requirements.log" 2>&1
) else (
    echo   requirements.lock missing — installing from requirements.txt
    pip install -r requirements.txt > "..\!LOG_DIR!\03a_pip_requirements.log" 2>&1
)
if %ERRORLEVEL% neq 0 ( popd & call :FAIL "pip install" "!LOG_DIR!\03a_pip_requirements.log" )
pip install pyinstaller > "..\!LOG_DIR!\03b_pip_pyinstaller.log" 2>&1
if %ERRORLEVEL% neq 0 ( popd & call :FAIL "pip install pyinstaller" "!LOG_DIR!\03b_pip_pyinstaller.log" )
popd
echo Dependencies installed.
echo.

:: ---------- Step 4: PyInstaller ----------
echo [4/5] Building KTHEALTHERP.exe...
pushd backend
pyinstaller hospital_erp.spec --clean --noconfirm > "..\!LOG_DIR!\04_pyinstaller.log" 2>&1
if %ERRORLEVEL% neq 0 ( popd & call :FAIL "pyinstaller" "!LOG_DIR!\04_pyinstaller.log" )
popd
if not exist "backend\dist\KTHEALTHERP.exe" (
    echo ERROR: KTHEALTHERP.exe was not created!
    type "!LOG_DIR!\04_pyinstaller.log" | more
    pause & exit /b 1
)

:: ---------- Step 5: Optional code signing ----------
echo [5/5] Code signing (optional)...
if "%SIGNING_CERT%"=="" (
    echo   SKIPPED ^(SIGNING_CERT not set^)
) else (
    if not defined SIGNING_TIMESTAMP set SIGNING_TIMESTAMP=http://timestamp.digicert.com
    echo   Signing with %SIGNING_CERT%
    signtool sign /f "%SIGNING_CERT%" /p "%SIGNING_PASS%" /tr "%SIGNING_TIMESTAMP%" /td sha256 /fd sha256 "backend\dist\KTHEALTHERP.exe" > "!LOG_DIR!\05_signtool.log" 2>&1
    if !ERRORLEVEL! neq 0 ( call :FAIL "signtool" "!LOG_DIR!\05_signtool.log" )
    signtool verify /pa "backend\dist\KTHEALTHERP.exe" >> "!LOG_DIR!\05_signtool.log" 2>&1
    if !ERRORLEVEL! neq 0 ( call :FAIL "signtool verify" "!LOG_DIR!\05_signtool.log" )
    echo   Signed and verified.
)
echo.

echo ============================================
echo  Build complete!
echo  Output:    backend\dist\KTHEALTHERP.exe
echo  Logs:      !LOG_DIR!\
echo ============================================
echo.
echo IMPORTANT: Always use this script to build.
echo Running PyInstaller directly will bundle the
echo OLD frontend and your UI changes won't appear.
echo.
echo To distribute the .exe directly: copy KTHEALTHERP.exe to any
echo folder and double-click it. The app will create a data\ folder
echo for the database and uploads.
echo.
echo To produce a Windows installer with Start Menu / Uninstaller
echo entries, run build_installer.bat after this completes.
echo.
pause
exit /b 0


:: ---------------------------------------------------------------
:: :FAIL "<step name>" "<log file>"
:: Tails the last 50 lines of the failed step's log and exits 1.
:: ---------------------------------------------------------------
:FAIL
echo.
echo ============================================
echo  BUILD FAILED at step: %~1
echo  Full log:  %~2
echo ============================================
echo  --- Last 50 lines of %~1 log ---
powershell -NoProfile -Command "Get-Content -Path '%~2' -Tail 50"
echo  --- end of log tail ---
echo.
pause
exit /b 1
