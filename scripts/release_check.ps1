$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { Write-Error 'Missing .venv. Run .\scripts\setup_windows.ps1 first.' }
& $Py -m compileall -q src app
& $Py -m pytest -q
& $Py -m src.system.release_check
