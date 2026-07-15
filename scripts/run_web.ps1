Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -ErrorAction SilentlyContinue
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "web")

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js/npm not found. Install Node.js 18+ from https://nodejs.org"
    exit 1
}

if (-not (Test-Path "node_modules")) {
    Write-Host "[PramaanHR Web] Installing dependencies..."
    npm install
}

Write-Host "[PramaanHR Web] Starting dev server with npm at http://localhost:5173"
Write-Host "[PramaanHR Web] Ensure the API server is running: python -m server.app"
npm run dev
