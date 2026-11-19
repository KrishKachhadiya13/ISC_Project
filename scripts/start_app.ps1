<#
.SYNOPSIS
    Start the whole StegaGuard website on Windows with one command.
.DESCRIPTION
    Starts the API (http://127.0.0.1:8000) in its own window and serves the
    production build of the UI at http://localhost:5173. Builds the UI first if
    needed. Close both windows (or press Ctrl+C here) to stop.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1
    powershell -ExecutionPolicy Bypass -File scripts\start_app.ps1 -Demo     # opens presenter mode
#>
param([switch]$Demo, [switch]$Rebuild, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

# Prefer the project's virtual environment; fall back to whatever `python` is on PATH.
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# Fewer BLAS threads keeps memory use modest; plenty for single-image requests.
$env:OPENBLAS_NUM_THREADS = "2"
$env:OMP_NUM_THREADS = "2"

if ($Rebuild -or -not (Test-Path (Join-Path $frontend "dist\index.html"))) {
    Write-Host "Building the UI..." -ForegroundColor Cyan
    Push-Location $frontend
    try { npm run build } finally { Pop-Location }
}

Write-Host "Starting the API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$api = Start-Process -FilePath $python -WorkingDirectory $backend `
    -ArgumentList @("-W", "ignore", "-m", "uvicorn", "app.main:app", "--port", "8000") -PassThru

# Wait until the API answers (it loads the models first, which takes a few seconds).
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
        $ready = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { Stop-Process -Id $api.Id -Force; throw "The API did not start. Run it manually to see the error." }
Write-Host ("API ready. Models loaded: " + ($health.models_loaded -join ", ")) -ForegroundColor Green

$url = "http://localhost:5173/"
if ($Demo) { $url = "http://localhost:5173/hide?demo=1" }
Write-Host "UI at $url  (Ctrl+C to stop)" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $url }

Push-Location $frontend
try { npm run preview } finally {
    Pop-Location
    if (-not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
