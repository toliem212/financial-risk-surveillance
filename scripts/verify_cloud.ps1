$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { Write-Error 'Missing .venv. Run .\scripts\setup_windows.ps1 first.' }
& $Py -m src.system.cloud_verify --write-test
