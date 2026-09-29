# Go-Live Runbook — v1.0.0-rc3.6

This document is the shortest path from a working local demo to an always-on cloud deployment.

## Gate A — local release

```powershell
.\scripts\setup_windows.ps1
.\scripts\run_demo.ps1
```

Confirm the dashboard opens and the fixture data populate every major domain.

## Gate B — public-source reachability

```powershell
.\scripts\smoke_live_sources.ps1
```

This is intentionally non-destructive. It only verifies public landing-page reachability/content hints. It does **not** prove every parser endpoint is unchanged.

Then run one real ingestion pass:

```powershell
.\scripts\run_live_once.ps1
```

Inspect `source_run` in the dashboard. A failed source must be visible as failed, not treated as zero activity.

## Gate C — Supabase credentials

Create a Supabase project, then put these values in local `.env` (never commit it):

```text
DATABASE_URL=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_RAW_BUCKET=raw-market-data
```

Recommended single `DATABASE_URL` for this project: **Shared Pooler / Session mode** from the Supabase Connect dialog. This works over IPv4 and is suitable for Streamlit as a persistent backend while also working for GitHub Actions.

## Gate D — cloud bootstrap

```powershell
.\scripts\bootstrap_cloud.ps1
```

The command is idempotent: it applies `schema/postgres.sql` and ensures the private raw Storage bucket exists.

Then verify real read/write connectivity:

```powershell
.\scripts\verify_cloud.ps1
```

The Storage write test uploads then deletes a tiny `_health/...txt` sentinel.

## Gate E — one complete go-live gate

When A–D are understood, run:

```powershell
.\scripts\go_live_gate.ps1
```

Do not move to scheduled automation until this gate completes cleanly or any source-specific failures are understood.

## Gate F — GitHub

Add repository Actions secrets:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Manually run, in this order:

1. **CI**
2. **Cloud verify**
3. **Market ingestion**
4. **VIRA semantic ingestion**
5. **Slow-moving macro context**
6. **Daily risk brief**

Only after manual runs are green should scheduled runs be enabled. Create repository variable `AUTOMATION_ENABLED=1`; until then cron-triggered jobs are deliberately skipped. Before enabling it, also run the manual **Live parser smoke** workflow.

## Gate G — Streamlit Community Cloud

Deploy `app/Home.py`.

Add `DATABASE_URL` through Streamlit Secrets. AI variables can remain absent/disabled. Do **not** add `SUPABASE_SERVICE_ROLE_KEY` to Streamlit; keep it in GitHub Actions/local admin only.

Verify:

- Home loads from PostgreSQL, not local SQLite;
- System Health shows cloud `source_run` records;
- Risk Feed loads;
- Daily Brief renders;
- Replay works;
- AI page says disabled unless intentionally enabled.

## Gate H — laptop-off proof

1. Close VS Code and turn off the local laptop.
2. Wait for at least one scheduled GitHub Actions ingestion window.
3. Open GitHub from another device and confirm the workflow completed.
4. Open the public Streamlit app and confirm a newer `source_run` timestamp than the laptop shutdown time.

This confirms that the system is cloud-operated rather than dependent on the developer laptop.

## Optional AI gate

Only after deterministic deployment is stable:

```text
AI_ENABLED=1
OPENAI_API_KEY=...
AI_MODEL=gpt-5.6-luna
```

The default model is deliberately the cost-sensitive GPT-5.6 Luna. Keep call/token caps enabled. ChatGPT Plus and API billing remain separate.

## Parser smoke before scheduled automation

Reachability is not enough. Before relying on cron, run a live **fetch + parse** smoke that writes nothing:

```powershell
.\scripts\smoke_live_parsers.ps1
```

Optionally choose a known HNX trading date:

```powershell
.\scripts\smoke_live_parsers.ps1 -Date 2026-09-29
```

The output separates `fetch_ok` from `parse_ok` for SBV OMO, HNX secondary/auction, each CBIS public page, VIRA latest bulletin and each SBV macro page. A website that returns HTTP 200 but changed schema will therefore fail `parse_ok` instead of silently entering production.
