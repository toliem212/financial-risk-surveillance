# Vietnam Financial Risk Surveillance System

**Release candidate: v1.0.0-rc3.6**

An automated near-real-time public-data surveillance system for Vietnam's money, FX and fixed-income markets. It focuses on public-market monitoring, data quality, event detection and point-in-time investigation.

## What the system does

```text
SBV / HNX Government Bonds / HNX CBIS / VIRA / slow-moving SBV macro context
                              ↓
                    Scheduled ingestion
                              ↓
                    Raw append-only archive
                              ↓
             Parse → Normalize → Validate/Reconcile
                              ↓
        Point-in-time observations + bond events + master data
                              ↓
                 Deterministic risk signal engine
                              ↓
     Risk Feed → Investigation → Historical Replay → Daily Brief
                              ↓
              Optional OpenAI enrichment (opt-in only)
```

### Surveillance domains

- **Money Market & Liquidity** — SBV OMO, VIRA IBOR/OMO context.
- **FX Pressure** — public USD/VND observations, policy-reference proximity and deterministic FX alerts.
- **Government Bonds / Rates** — HNX public trades, auctions, derived public-trade tenor curve and curve signals.
- **Corporate Bond Event Risk** — HNX CBIS issuer/bond identity, rating/disclosure/trading-status events and risk alerts.
- **Structural Macro Context** — latest public SBV M2, credit and LDR observations. These are context, not intraday alerts.

## Core product features

- append-only raw archive with content hashes;
- SQLite local development and PostgreSQL/Supabase cloud storage;
- incremental/idempotent ingestion;
- point-in-time fields and no-hindsight replay modes;
- VIRA daily/weekly semantic separation (`SNAPSHOT`, `FLOW`, `STOCK`);
- source reconciliation and explicit data-quality signals;
- unified Cross-Market Risk Feed and investigation workflow;
- Historical Replay (`SYSTEM_KNOWN` and `SOURCE_AVAILABLE` research mode);
- deterministic Daily Risk Brief with Markdown download;
- source-run/system-health history;
- optional OpenAI investigation/disclosure enrichment with token/call budgets and caching;
- GitHub Actions automation designed to run without the user's laptop.

## Important positioning

This is **not**:

- a Bloomberg/Refinitiv tick feed;
- a trading-signal or automated hedging system;
- an internal bank exposure, position, limit or P&L system;
- a claim that derived public-trade tenor yields are an official HNX yield curve.

The correct description is:

> **Automated near-real-time public-data financial risk surveillance and incident investigation.**

## Windows / VS Code quick start

The project does **not** need SQL Server/SSMS to run. Local runtime uses SQLite; cloud runtime uses PostgreSQL/Supabase.

From PowerShell in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_windows.ps1
.\scripts\run_demo.ps1
```

The demo opens Streamlit at:

```text
http://localhost:8501
```

For live public-source ingestion after the demo succeeds:

```powershell
.\scripts\run_live_once.ps1
.\scripts\start_dashboard.ps1
```

Full instructions: [`RUN_WINDOWS.md`](RUN_WINDOWS.md).

## Useful CLI commands

Preflight:

```bash
python -m src.system.preflight
```

SBV OMO:

```bash
python -m src.jobs.sbv_omo_once
```

HNX government bonds:

```bash
python -m src.jobs.hnx_gov_once --date 2026-09-29
```

HNX CBIS:

```bash
python -m src.jobs.hnx_cbonds_once
```

VIRA semantic ingestion:

```bash
python -m src.jobs.vira_once
```

Slow-moving SBV macro context:

```bash
python -m src.jobs.sbv_macro_once
```

Daily Risk Brief:

```bash
python -m src.jobs.generate_daily_brief
```

Historical Replay:

```bash
python -m src.jobs.replay_snapshot \
  --at 2026-09-29T16:30:00+07:00 \
  --mode SYSTEM_KNOWN
```

Streamlit:

```bash
streamlit run app/Home.py
```

## Data-quality conventions

Quality flags:

- `A` — direct authoritative/public-source observation/event;
- `B` — derived/reconciled with strong support;
- `C` — secondary/incomplete;
- `D` — review required;
- `X` — invalid/excluded.

Observation methods include `DIRECT_SOURCE`, `DIRECT_DAILY`, `DIRECT_WEEKLY_EOP`, `WEEKLY_AGGREGATE`, `DERIVED_RESIDUAL` and other explicitly labelled derivations.

VIRA weekly data are decomposed metric by metric; the system never treats an entire weekly bulletin as a single Friday observation.

## Historical Replay

`SYSTEM_KNOWN` is the default strict mode: only records actually observed/fetched by the pipeline before the cutoff are eligible.

`SOURCE_AVAILABLE` is a research reconstruction mode: it can include a public record that the project only ingested later during backfill, provided the source-publication timestamp was already eligible. The UI labels this distinction explicitly.

Current `bond_master` represents latest known master state and is therefore not used as historical state in Replay; timestamped `bond_event` records are used instead.

## Optional OpenAI layer

AI is **OFF by default**. The deterministic system works without any OpenAI API call.

Enable paid API calls only intentionally:

```text
AI_ENABLED=1
OPENAI_API_KEY=...
AI_MODEL=gpt-5.6-luna
```

Current AI features:

1. user-triggered Risk Investigation Copilot;
2. structured CBIS disclosure classification helper/fallback.

Controls include content-hash caching, daily call cap, input/output caps, structured output and usage logging. ChatGPT Plus and API billing are separate.

## Cloud deployment

Recommended low-cost stack:

```text
GitHub Actions → Supabase PostgreSQL/Storage → Streamlit Community Cloud
```

Run these in Supabase SQL Editor:

1. `schema/postgres.sql`
2. `schema/supabase_storage.sql`

Then configure GitHub secrets:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Tests run in CI when code changes; scheduled ingestion does **not** rerun the full test suite every 30 minutes.

Detailed deployment guide: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Automated workflows

- `ci.yml` — compile + test on code changes.
- `market_ingestion.yml` — SBV OMO + HNX Government Bonds + HNX CBIS every 30 minutes in the weekday monitoring window.
- `vira_ingestion.yml` — VIRA publication-window polling.
- `macro_context.yml` — slow-moving SBV macro context once per weekday.
- `daily_brief.yml` — deterministic end-of-day Markdown brief artifact.

Schedules are intentionally moderate because public websites are not contracted tick feeds and aggressive polling adds cost/load without improving information quality.

## Tests

```bash
pytest -q
python -m compileall -q src app
```

The release package includes offline fixtures so parser/business-logic regression tests do not depend on public websites being available during CI.

## Documentation

- [`RUN_WINDOWS.md`](RUN_WINDOWS.md) — local Windows/VS Code runbook.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — technical architecture.
- [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) — tables and core fields.
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — signal/data semantics.
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Supabase/GitHub/Streamlit deployment.
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — known limitations and guardrails.
- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) — concise project scope, workflow and demonstration guide.
- [`docs/SQL_EXAMPLES.md`](docs/SQL_EXAMPLES.md) / [`examples/queries.sql`](examples/queries.sql) — SQL examples.
- [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) — final deployment and release gate.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.

## Disclaimer

All market and event data are sourced from public information where accessible. The system contains no bank-internal positions, limits, P&L or proprietary exposure data. Thresholds are illustrative surveillance thresholds, not internal limits. Derived indicators and optional AI explanations are analytical aids, not investment recommendations.

## Go-live gate (rc3)

After local demo/live parsing succeeds and `.env` contains your Supabase credentials, the release includes an explicit end-to-end gate:

```powershell
.\scripts\go_live_gate.ps1
```

It performs: offline release tests → public-source reachability smoke → idempotent PostgreSQL/Storage bootstrap → cloud read/write verification → one live ingestion pass.

Cloud helpers can also be run separately:

```powershell
.\scripts\smoke_live_sources.ps1
.\scripts\bootstrap_cloud.ps1
.\scripts\verify_cloud.ps1
```

For one connection string shared by GitHub Actions and Streamlit Community Cloud, prefer the Supabase **Shared Pooler / Session mode** connection string. The Postgres adapter also disables Psycopg auto-prepared statements so transaction-pooler use does not silently fail after repeated queries.

Before enabling schedules, use the non-destructive parser smoke:

```powershell
.\scripts\smoke_live_parsers.ps1
```

This is stronger than a connectivity check: it fetches and parses the current public pages but writes nothing to the database or raw archive.

Security/secrets separation: [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

## Schedule safety

Scheduled GitHub workflows are **disabled by default**. Manual workflow runs always remain available. After cloud verification and manual ingestion succeed, create the GitHub repository variable:

```text
AUTOMATION_ENABLED=1
```

Only then will cron-based market/VIRA/macro/brief workflows execute. A separate **Live parser smoke** workflow can test current public-source fetch+parse behavior without writing database records.
