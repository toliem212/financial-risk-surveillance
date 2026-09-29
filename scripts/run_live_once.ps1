param(
    [string]$Date = (Get-Date -Format 'yyyy-MM-dd')
)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run .\scripts\setup_windows.ps1 first.' }

$env:APP_DATA_MODE = 'LIVE'
Write-Host "== LIVE public-source ingestion for $Date ==" -ForegroundColor Cyan
Write-Host 'LIVE never uses demo.db. If DATABASE_URL is empty, data goes to data/local/surveillance.db; otherwise it goes to PostgreSQL.' -ForegroundColor DarkGray

$jobs = @(
    @{ Name='SBV OMO'; Args=@('-m','src.jobs.sbv_omo_once') },
    @{ Name='HNX Government Bonds'; Args=@('-m','src.jobs.hnx_gov_once','--date',$Date) },
    @{ Name='HNX CBIS'; Args=@('-m','src.jobs.hnx_cbonds_once') },
    @{ Name='VIRA'; Args=@('-m','src.jobs.vira_once') },
    @{ Name='SBV Macro Context'; Args=@('-m','src.jobs.sbv_macro_once') }
)

foreach ($job in $jobs) {
    Write-Host "`n--- $($job.Name) ---" -ForegroundColor Yellow
    try {
        & $python @($job.Args)
        if ($LASTEXITCODE -ne 0) { Write-Warning "$($job.Name) exited with code $LASTEXITCODE" }
    } catch {
        Write-Warning "$($job.Name) failed: $($_.Exception.Message)"
    }
}

Write-Host "`n--- Preflight ---" -ForegroundColor Yellow
try { & $python -m src.system.preflight } catch { Write-Warning "Preflight failed: $($_.Exception.Message)" }

Write-Host "`n--- Daily Risk Brief ---" -ForegroundColor Yellow
$stamp = Get-Date -Format 'yyyy-MM-dd'
try { & $python -m src.jobs.generate_daily_brief --output "reports/daily-risk-brief-$stamp.md" | Out-Null } catch { Write-Warning "Brief failed: $($_.Exception.Message)" }

Write-Host "`nDone. Open LIVE dashboard with: .\scripts\start_dashboard.ps1" -ForegroundColor Green
