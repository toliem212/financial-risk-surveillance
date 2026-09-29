$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run .\scripts\setup_windows.ps1 first.' }

New-Item -ItemType Directory -Force -Path 'data\local' | Out-Null
New-Item -ItemType Directory -Force -Path 'data\raw\demo' | Out-Null
New-Item -ItemType Directory -Force -Path 'reports' | Out-Null

# DEMO is intentionally isolated from both live SQLite and cloud PostgreSQL.
$env:DATABASE_URL = ''
$env:SUPABASE_URL = ''
$env:SUPABASE_SERVICE_ROLE_KEY = ''
$env:LOCAL_DB_PATH = 'data/local/demo.db'
$env:APP_DATA_MODE = 'DEMO'
$db = 'data\local\demo.db'
if (Test-Path $db) { Remove-Item $db -Force }

Write-Host '== DEMO MODE: fixture data only; no live/cloud writes ==' -ForegroundColor Magenta
Write-Host 'Loading SBV OMO fixture...' -ForegroundColor Cyan
& $python -m src.jobs.sbv_omo_once --fixture tests/fixtures/sbv_omo_sample.html --db $db --raw-root data/raw/demo

Write-Host 'Loading HNX Government Bond fixture...' -ForegroundColor Cyan
& $python -m src.jobs.hnx_gov_once --date 2026-09-25 --secondary-fixture tests/fixtures/hnx_secondary_current.html --auction-fixture tests/fixtures/hnx_auction_sample.html --db $db --raw-root data/raw/demo

Write-Host 'Loading HNX CBIS fixture...' -ForegroundColor Cyan
& $python -m src.jobs.hnx_cbonds_once --issuer-fixture tests/fixtures/cbis_issuers_sample.html --bond-fixture tests/fixtures/cbis_bonds_sample.html --rating-fixture tests/fixtures/cbis_ratings_sample.html --disclosure-fixture tests/fixtures/cbis_disclosures_sample.html --status-fixture tests/fixtures/cbis_status_sample.html --db $db --raw-root data/raw/demo

Write-Host 'Loading VIRA fixture...' -ForegroundColor Cyan
& $python -m src.jobs.vira_once --daily-fixture tests/fixtures/vira_daily_sample.html --weekly-fixture tests/fixtures/vira_weekly_sample.html --db $db --raw-root data/raw/demo

Write-Host 'Loading SBV macro-context fixture...' -ForegroundColor Cyan
& $python -m src.jobs.sbv_macro_once --fixture-dir tests/fixtures/sbv_macro --db $db --raw-root data/raw/demo

Write-Host 'Generating demo Daily Risk Brief...' -ForegroundColor Cyan
& $python -m src.jobs.generate_daily_brief --db $db --output reports/demo-daily-risk-brief.md | Out-Null

Write-Host ''
Write-Host 'Opening Streamlit DEMO at http://localhost:8501' -ForegroundColor Green
& $python -m streamlit run app/Home.py
