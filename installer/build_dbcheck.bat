@echo off
setlocal EnableDelayedExpansion

:: Build the dbcheck.exe helper used by the installer wizard.
:: Output: installer\bin\dbcheck.exe
::
:: Requirements: backend\venv must exist (run install_and_setup.py first) so
:: pyinstaller and the cryptography package are available.

set REPO_ROOT=%~dp0..
set BACKEND_DIR=%REPO_ROOT%\backend
set OUT_DIR=%REPO_ROOT%\installer\bin
set SPEC_FILE=%REPO_ROOT%\installer\dbcheck\dbcheck.spec
set WORK_DIR=%REPO_ROOT%\installer\dbcheck\build
set DIST_DIR=%REPO_ROOT%\installer\dbcheck\dist

:: Prefer the project venv if it exists (dev workflow); otherwise fall back to
:: whatever python is on PATH (CI workflow — build_exe.bat installs deps into
:: the system interpreter via `pip install`, so PyInstaller is already there).
set VENV_PY=%BACKEND_DIR%\venv\Scripts\python.exe
if exist "%VENV_PY%" (
    set PY=%VENV_PY%
) else (
    set PY=python
)

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Building dbcheck.exe ...
"%PY%" -m PyInstaller --noconfirm --clean ^
    --distpath "%DIST_DIR%" ^
    --workpath "%WORK_DIR%" ^
    "%SPEC_FILE%"
if %ERRORLEVEL% neq 0 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

copy /Y "%DIST_DIR%\dbcheck.exe" "%OUT_DIR%\dbcheck.exe" >nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Could not copy dbcheck.exe to %OUT_DIR%
    exit /b 1
)

echo Done: %OUT_DIR%\dbcheck.exe
exit /b 0
