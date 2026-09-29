# Windows / VS Code Runbook

This is the complete local handoff for **v1.0.0-rc3.6**.

## 1. Database note

You do **not** need Microsoft SQL Server / SSMS to run this repository.

- Local: SQLite at `data/local/surveillance.db`.
- Cloud / always-on: PostgreSQL through Supabase.
- SSMS can remain installed for SQL practice or other projects.

## 2. Open the project

Extract the ZIP. The VS Code folder you open must contain:

```text
README.md
requirements.txt
src\
app\
tests\
scripts\
schema\
```

In VS Code choose **File → Open Folder** and select `financial-risk-surveillance`.

Open **Terminal → New Terminal** (PowerShell) and verify:

```powershell
python --version
git --version
```

Python 3.11+ is required; Python 3.12 is the cloud/CI target.

## 3. One-time setup

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_windows.ps1
```

The setup script:

1. creates `.venv`;
2. installs dependencies;
3. copies `.env.example` to `.env` if needed;
4. compiles Python files;
5. runs the regression tests;
6. runs local database preflight;
7. runs the offline end-to-end release check.

## 4. Safe offline demo

```powershell
.\scripts\run_demo.ps1
```

This intentionally resets only the local demo SQLite database and loads bundled fixtures for:

- SBV OMO;
- HNX Government Bonds;
- HNX CBIS;
- VIRA;
- slow-moving SBV M2/credit/LDR context.

It also generates `reports/demo-daily-risk-brief.md`, runs preflight and starts Streamlit.

Open:

```text
http://localhost:8501
```

Expected pages/features:

- Home / System Health;
- Cross-Market Risk Feed;
- Daily Risk Brief;
- AI Usage & Budget;
- Historical Replay;
- OMO / FX / Rates / Corporate Bond / Macro Context sections.

Press `Ctrl+C` to stop Streamlit.

## 5. Run live public sources

After the fixture demo succeeds:

```powershell
.\scripts\run_live_once.ps1
```

Or specify the HNX government-bond date:

```powershell
.\scripts\run_live_once.ps1 -Date 2026-09-29
```

The script tries all public workers, runs preflight and writes a deterministic brief under `reports/`.

Then:

```powershell
.\scripts\start_dashboard.ps1
```

Public websites can change HTML, have no record for a date, reject automated traffic or temporarily fail. A source failure must appear as a failed source run; never interpret a failed scrape as zero market activity.

## 6. Local data locations

Database:

```text
data\local\surveillance.db
```

Raw archive:

```text
data\raw\
```

Generated reports:

```text
reports\
```

Do not delete the SQLite file if you want to preserve locally accumulated history.

## 7. Preflight on demand

```powershell
.\scripts\preflight.ps1
```

or:

```powershell
.\.venv\Scripts\python.exe -m src.system.preflight
```

## 8. Move to Supabase after local live ingestion works

Create a Supabase project and copy `.env.example` values into your private `.env`. Prefer the **Shared Pooler / Session mode** `DATABASE_URL` for one URL shared by GitHub Actions and Streamlit.

Then run:

```powershell
.\scripts\bootstrap_cloud.ps1
.\scripts\verify_cloud.ps1
```

For the complete release-to-cloud gate:

```powershell
.\scripts\go_live_gate.ps1
```

Full sequence: [`docs/GO_LIVE.md`](docs/GO_LIVE.md).

## 9. GitHub Actions / always-on automation

Add repository secrets:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Manually run **Cloud verify** and every ingestion workflow once before relying on schedules.

## 10. Streamlit Cloud

Deploy `app/Home.py`. In Streamlit Secrets provide `DATABASE_URL` (plus optional AI settings only). Do not expose the Supabase service-role key to the public app.

## 11. OpenAI remains optional

Keep `AI_ENABLED=0` until deterministic cloud operation is stable. Default optional model: `gpt-5.6-luna`. API usage is separately billed from ChatGPT Plus.


## PowerShell compatibility

Release rc3.1 stores `.ps1` files as UTF-8 with BOM and keeps console strings ASCII-only so they parse correctly in Windows PowerShell 5.1 as well as PowerShell 7. The Streamlit application itself remains Vietnamese-first.
