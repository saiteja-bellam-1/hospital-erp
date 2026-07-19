# KT HEALTH ERP - one-shot local runner (Windows / PowerShell)
# Installs deps, seeds a fresh dev DB, and launches all 4 processes in
# separate windows: hospital backend/frontend + license-manager backend/frontend.
#
# Robust against a fresh machine where PATH hasn't refreshed after installing
# Python/Node: it locates the real python.exe / node on disk, ignoring the
# Microsoft Store "python" alias stub.
#
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File .\run_all.ps1
#
# Admin login after it comes up:  admin / admin123  at http://localhost:3003

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Section($msg) { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }

# --- Find a REAL python.exe (not the Microsoft Store alias) ---
# Returns the full path to python.exe, or $null.
function Find-PythonExe {
    # 1) py launcher (most reliable when present)
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $v = & $py.Source -3 -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
        } catch {}
    }
    # 2) filesystem search of standard install locations
    $globs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "C:\Program Files\Python3*\python.exe",
        "C:\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    # 3) plain 'python' on PATH, but reject the WindowsApps store stub
    $p = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($p -and $p.Source -notmatch "WindowsApps") {
        try {
            $v = & $p.Source -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
        } catch {}
    }
    return $null
}

# --- Ensure npm is reachable, adding the default Node dir to PATH if needed ---
function Ensure-Npm {
    if (Get-Command npm -ErrorAction SilentlyContinue) { return }
    $nodeDir = "C:\Program Files\nodejs"
    if (Test-Path (Join-Path $nodeDir "npm.cmd")) {
        $env:Path = "$nodeDir;$env:Path"
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found. Open a NEW PowerShell window (so PATH refreshes) and re-run this script."
    }
}

$PyExe = Find-PythonExe
if (-not $PyExe) {
    throw "Real Python not found. Run bootstrap_and_run.ps1 first (it installs Python), then re-run in a NEW PowerShell window."
}
Ensure-Npm
Write-Host "Using Python: $PyExe"
Write-Host "Using npm:    $((Get-Command npm).Source)"

# =====================================================================
# 1) Hospital backend: venv + deps + seed
# =====================================================================
Section "Hospital backend: venv + dependencies"
$Backend = Join-Path $Root "backend"
$BackendPy = Join-Path $Backend "venv\Scripts\python.exe"
if (-not (Test-Path $BackendPy)) {
    & $PyExe -m venv (Join-Path $Backend "venv")
}
& $BackendPy -m pip install --upgrade pip
& $BackendPy -m pip install -r (Join-Path $Backend "requirements.lock")

Section "Hospital backend: seed fresh DB (admin/admin123)"
Push-Location $Backend
& $BackendPy "seed_dev.py"
Pop-Location

# =====================================================================
# 2) License-manager backend: venv + deps
# =====================================================================
Section "License Manager backend: venv + dependencies"
$LmBackend = Join-Path $Root "license-manager\backend"
$LmPy = Join-Path $LmBackend "venv\Scripts\python.exe"
if (-not (Test-Path $LmPy)) {
    & $PyExe -m venv (Join-Path $LmBackend "venv")
}
& $LmPy -m pip install --upgrade pip
& $LmPy -m pip install -r (Join-Path $LmBackend "requirements.txt")

# =====================================================================
# 3) Frontend deps
# =====================================================================
Section "Hospital frontend: npm install"
Push-Location (Join-Path $Root "frontend")
npm install
Pop-Location

Section "License Manager frontend: npm install"
Push-Location (Join-Path $Root "license-manager\frontend")
npm install
Pop-Location

# =====================================================================
# 4) Launch all 4 processes as tabs in ONE Windows Terminal window
#    (falls back to separate PowerShell windows if wt.exe is missing).
# =====================================================================
Section "Launching all services"

$FrontEnd   = Join-Path $Root "frontend"
$LmFrontEnd = Join-Path $Root "license-manager\frontend"

if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
    $wtArgs = "new-tab --title ERP-API -d $Backend powershell -NoExit -Command .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 " +
              "; new-tab --title ERP-UI -d $FrontEnd powershell -NoExit -Command npm.cmd run start " +
              "; new-tab --title LM-API -d $LmBackend powershell -NoExit -Command .\venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 9000 " +
              "; new-tab --title LM-UI -d $LmFrontEnd powershell -NoExit -Command npm.cmd run start"
    Start-Process wt.exe -ArgumentList $wtArgs
    Write-Host "`nAll services launching as tabs in one Windows Terminal window." -ForegroundColor Green
} else {
    # Fallback: Windows Terminal not installed -> separate windows.
    Start-Process powershell -ArgumentList @("-NoExit","-Command","cd '$Backend'; .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000")
    Start-Process powershell -ArgumentList @("-NoExit","-Command","cd '$FrontEnd'; npm.cmd run start")
    Start-Process powershell -ArgumentList @("-NoExit","-Command","cd '$LmBackend'; .\venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 9000")
    Start-Process powershell -ArgumentList @("-NoExit","-Command","cd '$LmFrontEnd'; npm.cmd run start")
    Write-Host "`nWindows Terminal not found - launched services in separate windows." -ForegroundColor Yellow
}
Write-Host "  Hospital ERP UI:      http://localhost:3003   (login: admin / admin123)"
Write-Host "  Hospital API:         http://localhost:8000/docs"
Write-Host "  License Manager UI:   http://localhost:3000"
Write-Host "  License Manager API:  http://localhost:9000/api/dashboard"
