@echo off
setlocal EnableDelayedExpansion
echo ============================================
echo  KT HEALTH ERP - Windows Installer Builder
echo ============================================
echo.

:: Requires Inno Setup 6+. Download: https://jrsoftware.org/isinfo.php
:: Looks for ISCC.exe in the standard install locations and on PATH.

if not exist "backend\dist\KTHEALTHERP.exe" (
    echo ERROR: backend\dist\KTHEALTHERP.exe not found.
    echo Run build_exe.bat first to produce the .exe.
    pause & exit /b 1
)

:: Build the wizard's pre-install helper if it isn't already in installer\bin.
:: dbcheck.exe is shelled out by the Inno Setup [Code] section to do the
:: machine-id readout, license dry-run, DB integrity check, and writability probes.
if not exist "installer\bin\dbcheck.exe" (
    echo installer\bin\dbcheck.exe not found — building...
    call installer\build_dbcheck.bat
    if errorlevel 1 (
        echo ERROR: dbcheck.exe build failed
        pause & exit /b 1
    )
)

set ISCC=
where ISCC.exe >nul 2>&1 && set ISCC=ISCC.exe
if "%ISCC%"=="" if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo ERROR: Inno Setup compiler ^(ISCC.exe^) not found.
    echo Install Inno Setup 6+ from https://jrsoftware.org/isinfo.php
    pause & exit /b 1
)

:: Version — single source of truth is backend\app\version.py (APP_VERSION).
:: Read it so the installer filename + AppVersion always match the .exe build.
:: Override with: set INSTALLER_VERSION=1.2.0 before running.
if not defined INSTALLER_VERSION (
    for /f "tokens=2 delims== " %%V in ('findstr /b "APP_VERSION" backend\app\version.py') do (
        set INSTALLER_VERSION=%%~V
    )
)
if not defined INSTALLER_VERSION set INSTALLER_VERSION=1.1.0

echo Using ISCC: %ISCC%
echo Version:    %INSTALLER_VERSION%
echo.

%ISCC% /DAppVersion=%INSTALLER_VERSION% installer\installer.iss
if %ERRORLEVEL% neq 0 (
    echo ERROR: Inno Setup compilation failed
    pause & exit /b 1
)

echo.
echo ============================================
echo  Installer built!
echo  Output: backend\dist\installer\KTHEALTHERP_Setup_%INSTALLER_VERSION%.exe
echo ============================================
echo.

:: Optional code signing on the installer itself (separate from the inner .exe)
if not "%SIGNING_CERT%"=="" (
    if not defined SIGNING_TIMESTAMP set SIGNING_TIMESTAMP=http://timestamp.digicert.com
    echo Signing installer...
    signtool sign /f "%SIGNING_CERT%" /p "%SIGNING_PASS%" /tr "%SIGNING_TIMESTAMP%" /td sha256 /fd sha256 "backend\dist\installer\KTHEALTHERP_Setup_%INSTALLER_VERSION%.exe"
    if !ERRORLEVEL! neq 0 (
        echo ERROR: signtool failed on installer
        pause & exit /b 1
    )
    echo Installer signed.
) else (
    echo NOTE: Installer not signed ^(SIGNING_CERT not set^).
)

pause
