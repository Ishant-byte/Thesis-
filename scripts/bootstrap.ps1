# PramaanHR bootstrap (Windows PowerShell)
# Creates venv, installs dependencies.

$ErrorActionPreference = "Stop"

Write-Host "[PramaanHR] Bootstrapping..." -ForegroundColor Cyan

if (!(Test-Path .\requirements.txt)) {
  Write-Host "Run this from the project root (where requirements.txt exists)." -ForegroundColor Red
  exit 1
}

if (!(Test-Path .\.venv)) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Host "" 
Write-Host "[PramaanHR] Done." -ForegroundColor Green
Write-Host "Next:" -ForegroundColor Green
Write-Host "  1) Start MongoDB (mongod)" 
Write-Host "  2) Terminal A: python -m server.app" 
Write-Host "  3) Terminal B (web):  scripts\run_web.ps1   → http://localhost:5173"
Write-Host "     or (desktop):     python -m client.main"
