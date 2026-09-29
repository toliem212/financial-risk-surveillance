param(
    [ValidateSet('Live','Demo')]
    [string]$Mode = 'Live'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run .\scripts\setup_windows.ps1 first.' }

if ($Mode -eq 'Demo') {
    $env:DATABASE_URL = ''
    $env:SUPABASE_URL = ''
    $env:SUPABASE_SERVICE_ROLE_KEY = ''
    $env:LOCAL_DB_PATH = 'data/local/demo.db'
    $env:APP_DATA_MODE = 'DEMO'
    Write-Host 'Opening dashboard in DEMO mode (data/local/demo.db).' -ForegroundColor Magenta
} else {
    $env:APP_DATA_MODE = 'LIVE'
    Write-Host 'Opening dashboard in LIVE mode.' -ForegroundColor Green
}

& $python -m streamlit run app/Home.py
