<#
.SYNOPSIS
    Cross-platform Windows PowerShell task runner for StegaGuard.
.DESCRIPTION
    Provides equivalent commands to GNU Make on Windows.
#>

param (
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

switch ($Command.ToLower()) {
    "test" {
        Write-Host "Running backend tests..." -ForegroundColor Cyan
        $env:PYTHONPATH = "backend"
        python -m pytest backend/tests -v
    }
    "lint" {
        Write-Host "Running ruff check..." -ForegroundColor Cyan
        python -m ruff check backend
        Write-Host "Checking code formatting..." -ForegroundColor Cyan
        python -m ruff format backend --check
        Write-Host "Running mypy..." -ForegroundColor Cyan
        python -m mypy backend/app
        Write-Host "All lint and type checks passed!" -ForegroundColor Green
    }
    "format" {
        Write-Host "Fixing and formatting with ruff..." -ForegroundColor Cyan
        python -m ruff check backend --fix
        python -m ruff format backend
        Write-Host "Formatting complete!" -ForegroundColor Green
    }
    "run-backend" {
        Write-Host "Starting StegaGuard backend on http://localhost:8000..." -ForegroundColor Cyan
        $env:PYTHONPATH = "backend"
        python -m uvicorn app.main:app --reload --port 8000
    }
    "run-frontend" {
        Write-Host "Starting StegaGuard frontend on http://localhost:5173..." -ForegroundColor Cyan
        Set-Location frontend
        npm run dev
    }
    "setup" {
        Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
        python -m pip install -r backend/requirements.txt
        python -m pip install -r backend/requirements-dev.txt
        Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
        Set-Location frontend
        npm install
        Set-Location ..
    }
    default {
        Write-Host "StegaGuard Windows PowerShell Runner" -ForegroundColor Yellow
        Write-Host "Usage: .\scripts\run.ps1 <command>"
        Write-Host "Commands:"
        Write-Host "  test         Run backend tests"
        Write-Host "  lint         Run ruff and mypy checks"
        Write-Host "  format       Format code with ruff"
        Write-Host "  run-backend  Start FastAPI backend"
        Write-Host "  run-frontend Start Vite React frontend"
        Write-Host "  setup        Install backend and frontend dependencies"
    }
}
