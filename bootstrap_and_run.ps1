# KT HEALTH ERP - full bootstrap for a fresh Windows machine.
# Installs Python 3.12 + Node.js LTS (via winget) if genuinely missing, then
# hands off to run_all.ps1 which installs app deps, seeds the DB, and launches
# all 4 services.
#
# This version ignores the Microsoft Store "python" alias stub, so it won't be
# tricked into skipping the real Python install.
#
# Usage (from the project root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\bootstrap_and_run.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

function Section($msg) { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path","Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path","User")
    $env:Path = "$machine;$user"
}

# Detect a REAL python.exe (not the WindowsApps store alias). Returns path or $null.
function Find-PythonExe {
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $v = & $py.Source -3 -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
        } catch {}
    }
    $globs = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "C:\Program Files\Python3*\python.exe",
        "C:\Python3*\python.exe"
    )
    foreach ($g in $globs) {
        $hit = Get-ChildItem $g -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    $p = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($p -and $p.Source -notmatch "WindowsApps") {
        try {
            $v = & $p.Source -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
        } catch {}
    }
    return $null
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "winget not found. Install 'App Installer' from the Microsoft Store, then re-run." -ForegroundColor Red
    exit 1
}

# =====================================================================
# 1) Python
# =====================================================================
Section "Checking Python (ignoring the Microsoft Store stub)"
if (-not (Find-PythonExe)) {
    Write-Host "Installing Python 3.12 (user scope, no admin needed) ..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    Refresh-Path
} else {
    Write-Host "Real Python already present: $(Find-PythonExe)"
}

# =====================================================================
# 2) Node.js
# =====================================================================
Section "Checking Node.js"
if (-not (Get-Command node -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\nodejs\node.exe")) {
    Write-Host "Installing Node.js LTS ..."
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    Refresh-Path
} else {
    Write-Host "Node.js already present."
}

Refresh-Path

# =====================================================================
# 3) Verify + hand off
# =====================================================================
Section "Verifying toolchain"
$PyExe = Find-PythonExe
if (-not $PyExe) {
    Write-Host "Python still not detected. Close this window, open a NEW PowerShell, and run:  .\run_all.ps1" -ForegroundColor Yellow
    exit 0
}
Write-Host "Python: $PyExe"
& $PyExe --version

Section "Installing app dependencies and launching services"
& (Join-Path $Root "run_all.ps1")
