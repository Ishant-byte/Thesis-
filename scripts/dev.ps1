$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $Root "web"
$HealthUrl = "http://127.0.0.1:8765/health"

function Test-ApiServer {
  try {
    Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 -ErrorAction Stop | Out-Null
    return $true
  } catch {
    return $false
  }
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error "npm was not found. Install Node.js 18+ or reopen PowerShell after installing Node.js."
  exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Error "python was not found. Install Python 3.10+ or add it to PATH."
  exit 1
}

if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
  Write-Host "[PramaanHR] Installing web dependencies..."
  npm install --prefix $WebDir
}

if (Test-ApiServer) {
  Write-Host "[PramaanHR] API server already running at http://127.0.0.1:8765"
} else {
  Write-Host "[PramaanHR] Starting API server at http://127.0.0.1:8765..."
  $serverJob = Start-Job -Name "PramaanHR API" -ScriptBlock {
    param($ProjectRoot)
    Set-Location $ProjectRoot
    python -m server.app
  } -ArgumentList $Root

  $ready = $false
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-ApiServer) {
      $ready = $true
      break
    }
    if ($serverJob.State -ne "Running") {
      break
    }
  }

  if (-not $ready) {
    Write-Host "[PramaanHR] API server failed to start. Recent output:"
    Receive-Job -Job $serverJob -Keep
    Write-Error "Start MongoDB first, then run npm run dev again."
    exit 1
  }
}

Write-Host "[PramaanHR] Starting web app with npm at http://localhost:5173"
npm run dev --prefix $WebDir
