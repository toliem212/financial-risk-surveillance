$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) { Write-Error 'Missing .venv. Run .\scripts\setup_windows.ps1 first.' }

Write-Host '== 1/6 Local release gate ==' -ForegroundColor Cyan
& $Py -m compileall -q src app
& $Py -m pytest -q
& $Py -m src.system.release_check

Write-Host "`n== 2/6 Public-source reachability smoke ==" -ForegroundColor Cyan
& $Py -m src.system.live_source_smoke
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'At least one public source is currently unreachable. Fix/understand this before relying on scheduled live ingestion.'
}

Write-Host "`n== 3/6 Live parser smoke (non-destructive) ==" -ForegroundColor Cyan
& $Py -m src.system.live_parser_smoke
if ($LASTEXITCODE -ne 0) { Write-Warning 'One or more live parsers failed. Review before scheduled deployment.' }

Write-Host "`n== 4/6 Cloud bootstrap ==" -ForegroundColor Cyan
& $Py -m src.system.cloud_bootstrap --apply

Write-Host "`n== 5/6 Cloud verify ==" -ForegroundColor Cyan
& $Py -m src.system.cloud_verify --write-test

Write-Host "`n== 6/6 One live ingestion pass ==" -ForegroundColor Cyan
& "$Root\scripts\run_live_once.ps1"

Write-Host "`nGO-LIVE GATE COMPLETE" -ForegroundColor Green
Write-Host 'Now start the dashboard locally with: .\scripts\start_dashboard.ps1'
Write-Host 'Then push the same code to GitHub and manually run the cloud workflows once before enabling reliance on schedules.'
