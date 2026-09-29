$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { Write-Error 'Missing .venv. Run .\scripts\setup_windows.ps1 first.' }
Write-Host 'Dry-run cloud bootstrap...' -ForegroundColor Cyan
& $Py -m src.system.cloud_bootstrap
Write-Host ''
Write-Host 'Applying idempotent PostgreSQL schema and ensuring raw Storage bucket...' -ForegroundColor Yellow
& $Py -m src.system.cloud_bootstrap --apply
Write-Host ''
Write-Host 'Verifying cloud connectivity...' -ForegroundColor Cyan
& $Py -m src.system.cloud_verify --write-test
