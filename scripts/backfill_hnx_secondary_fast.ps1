param(
    [Parameter(Mandatory=$true)]
    [string]$StartDate,

    [Parameter(Mandatory=$true)]
    [string]$EndDate,

    [int]$SleepMs = 200
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python environment not found: $Python"
}

Push-Location $Root
try {
    & $Python -m src.jobs.hnx_gov_secondary_backfill `
        --start-date $StartDate `
        --end-date $EndDate `
        --sleep-ms $SleepMs

    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
