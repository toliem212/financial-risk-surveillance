$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host '== Vietnam Financial Risk Surveillance: Windows setup ==' -ForegroundColor Cyan

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}

$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Virtual environment Python not found.' }

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
& $python -m compileall -q src app
& $python -m pytest -q
& $python -m src.system.preflight
& $python -m src.system.release_check

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host 'Next: .\scripts\run_demo.ps1'
