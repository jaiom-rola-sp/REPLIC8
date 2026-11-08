# Start the REPLIC8 backend on Windows, showing the gateway address and admin token first.
#
#   cd backend
#   powershell -ExecutionPolicy Bypass -File .\start.ps1
#
# Reads backend\.env (never committed). If it has no admin token, one is made and saved there.
# The admin token is shown on this screen and copied to the clipboard: don't run this while screen-sharing.
# Leave the window open while the backend runs; Ctrl+C stops it.

$ErrorActionPreference = "Continue"  # "Stop" would turn docker/tailscale stderr into a crash on Windows PowerShell 5
Set-Location -Path $PSScriptRoot
$envFile = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "No .env file in $PSScriptRoot. Copy .env.example to .env and fill it in." -ForegroundColor Red
    exit 1
}

# 1. Make sure there is an admin token (a new random one if the line is missing or empty).
$lines = @(Get-Content $envFile)
$adminLine = $lines | Where-Object { $_ -match '^\s*REPLIC8_ADMIN_TOKENS\s*=\s*\S' } | Select-Object -First 1
if (-not $adminLine) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $newToken = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    $lines = @($lines | Where-Object { $_ -notmatch '^\s*REPLIC8_ADMIN_TOKENS\s*=' }) + "REPLIC8_ADMIN_TOKENS=$newToken"
    Set-Content -Path $envFile -Value $lines
    Write-Host "No admin token was set, so a new one was made and saved in .env." -ForegroundColor Yellow
}

# 2. Load every NAME=value line into this window's environment.
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
        $value = $Matches[2].Trim().Trim("'").Trim('"')
        Set-Item -Path "env:$($Matches[1])" -Value $value
    }
}

foreach ($name in @("REPLIC8_GATEWAY_TOKENS", "REPLIC8_ADMIN_TOKENS")) {
    if (-not (Get-Item -Path "env:$name" -ErrorAction SilentlyContinue).Value) {
        Write-Host "$name is empty in .env. Fill it in and run this again." -ForegroundColor Red
        exit 1
    }
}
$admin = ($env:REPLIC8_ADMIN_TOKENS -split ',')[0].Trim()

# 3. Docker must be running (legacy code only runs in its sandbox).
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker isn't running. Start Docker Desktop, wait for 'Engine running', then run this again." -ForegroundColor Red
    exit 1
}

# 4. Build the sandbox image from this checkout, so it always matches the code (a few seconds when
#    nothing changed; several minutes the first time). The backend then pins this exact build itself.
Write-Host "Building the sandbox image (cached if nothing changed)..."
docker build -q -t replic8-legacy-runtime:1 (Join-Path $PSScriptRoot "runtime") | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "The sandbox image did not build. Run this to see why:  docker build -t replic8-legacy-runtime:1 runtime" -ForegroundColor Red
    exit 1
}
if ($env:REPLIC8_SANDBOX_IMAGES) {
    Remove-Item -Path env:REPLIC8_SANDBOX_IMAGES
    Write-Host "Ignoring REPLIC8_SANDBOX_IMAGES from .env so the image just built is the one used." -ForegroundColor Yellow
}

# 5. Nothing else may be using the port.
$port = if ($env:REPLIC8_PORT) { [int]$env:REPLIC8_PORT } else { 8000 }
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Something is already running on port $port (probably the backend in another window)." -ForegroundColor Red
    Write-Host "Close that window, or stop it with:" -ForegroundColor Red
    Write-Host "  Get-NetTCPConnection -LocalPort $port -State Listen | ForEach-Object { Stop-Process -Id `$_.OwningProcess -Force }"
    exit 1
}

# 6. Show what the dashboard needs.
$address = $null
if (Get-Command tailscale -ErrorAction SilentlyContinue) {
    $funnel = (tailscale funnel status 2>$null) -join "`n"
    if ($funnel -match '(https://[A-Za-z0-9.-]+\.ts\.net)') { $address = $Matches[1] }
}
if (-not $address) { $address = "(Tailscale Funnel is not on: run  tailscale funnel --bg $port)" }

Write-Host ""
Write-Host "================ REPLIC8 ================" -ForegroundColor Cyan
Write-Host "Gateway address : $address"
Write-Host "Admin token     : $admin"
Write-Host "=========================================" -ForegroundColor Cyan
try { Set-Clipboard -Value $admin; Write-Host "The admin token is copied: paste it with Ctrl+V into 'Admin token'." -ForegroundColor Green } catch { }
Write-Host "Keep the admin token private. Give judges a workspace token (r8w_...) instead."
Write-Host ""

# 7. Start the backend (Ctrl+C stops it).
python -m replic8
