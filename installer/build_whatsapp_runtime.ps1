<#
 Stages the WhatsApp runtime for the installer:

   installer\bin\node\node.exe          portable Node.js (win-x64), SHA-256 verified
   installer\bin\whatsapp-sidecar\...   sidecar source + production node_modules

 Nothing needs to be installed on the customer machine: no Node, no npm, no
 internet. The installer copies both folders next to KTHEALTHERP.exe, where
 backend\app\services\whatsapp_service.py looks for them.

 Env overrides:
   NODE_MAJOR    Node major line to ship (default 22 = LTS; Baileys needs >= 20)
   NODE_VERSION  exact version, e.g. 22.23.5 (default: newest of NODE_MAJOR)
#>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$repo    = Resolve-Path (Join-Path $PSScriptRoot '..')
$sidecar = Join-Path $repo 'whatsapp-sidecar'
$out     = Join-Path $PSScriptRoot 'bin'
$nodeOut = Join-Path $out 'node'
$scOut   = Join-Path $out 'whatsapp-sidecar'
$work    = Join-Path $PSScriptRoot 'whatsapp-build'

$major = if ($env:NODE_MAJOR) { $env:NODE_MAJOR } else { '22' }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---- resolve + download Node ------------------------------------------------
if ($env:NODE_VERSION) {
    $base = "https://nodejs.org/dist/v$($env:NODE_VERSION)"
} else {
    $base = "https://nodejs.org/dist/latest-v$major.x"
}
$sums = (Invoke-WebRequest -UseBasicParsing "$base/SHASUMS256.txt").Content -split "`n"
$line = $sums | Where-Object { $_ -match 'node-v[\d.]+-win-x64\.zip\s*$' } | Select-Object -First 1
if (-not $line) { throw "No win-x64 zip listed at $base" }
$hash, $zipName = ($line.Trim() -split '\s+')
Write-Host "Node archive: $zipName"

Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $work | Out-Null
$zip = Join-Path $work $zipName
Invoke-WebRequest -UseBasicParsing "$base/$zipName" -OutFile $zip
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $hash.ToLower()) { throw "SHA-256 mismatch for $zipName (expected $hash, got $actual)" }

Expand-Archive $zip -DestinationPath $work -Force
$nodeExe = Get-ChildItem $work -Recurse -Filter node.exe | Select-Object -First 1
if (-not $nodeExe) { throw 'node.exe not found in archive' }

# ---- stage Node (node.exe only; npm is not needed at runtime) ----------------
Remove-Item $nodeOut -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $nodeOut | Out-Null
Copy-Item $nodeExe.FullName (Join-Path $nodeOut 'node.exe')
$nodeLicense = Get-ChildItem (Split-Path $nodeExe.FullName) -Filter LICENSE -ErrorAction SilentlyContinue | Select-Object -First 1
if ($nodeLicense) { Copy-Item $nodeLicense.FullName (Join-Path $nodeOut 'LICENSE') }
& (Join-Path $nodeOut 'node.exe') --version

# ---- stage sidecar with production dependencies ------------------------------
Remove-Item $scOut -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $scOut | Out-Null
foreach ($f in 'index.js', 'package.json', 'package-lock.json') {
    Copy-Item (Join-Path $sidecar $f) $scOut
}
Push-Location $scOut
try {
    npm ci --omit=dev --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
} finally { Pop-Location }

# ---- smoke test: the staged runtime must load Baileys -----------------------
Push-Location $scOut
try {
    & (Join-Path $nodeOut 'node.exe') --input-type=module -e "import('@whiskeysockets/baileys').then(()=>console.log('baileys ok'))"
    if ($LASTEXITCODE -ne 0) { throw 'staged node.exe cannot load Baileys' }
} finally { Pop-Location }

Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "WhatsApp runtime staged in $out"
