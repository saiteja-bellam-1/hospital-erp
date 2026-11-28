@echo off
:: Stage portable Node.js + the WhatsApp sidecar into installer\bin\ for Inno Setup.
:: Needs internet + npm on the BUILD machine only (CI already has both).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_whatsapp_runtime.ps1"
if %ERRORLEVEL% neq 0 (
    echo ERROR: WhatsApp runtime staging failed
    exit /b 1
)
