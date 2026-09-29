# Deployment Guide — Supabase + GitHub Actions + Streamlit

## 1. Local gate

Before cloud deployment:

```powershell
.\scripts\setup_windows.ps1
.\scripts\run_demo.ps1
```

Then run one live pass and confirm source failures/successes are visible in `source_run`.

## 2. Supabase

Create a Free project.

For a single connection string shared by GitHub Actions and Streamlit, use the **Shared Pooler / Session mode** connection string from Supabase Connect. The application also disables Psycopg auto-prepared statements, so transaction-pooler use remains compatible if you intentionally choose it.

Put `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in local `.env`, then bootstrap idempotently:

```powershell
.\scripts\bootstrap_cloud.ps1
```

This applies `schema/postgres.sql` and ensures the private raw Storage bucket exists.

Run locally with temporary environment variables:

```powershell
$env:DATABASE_URL='...'
$env:SUPABASE_URL='...'
$env:SUPABASE_SERVICE_ROLE_KEY='...'
.\scripts\preflight.ps1
```

Then run `.\scripts\verify_cloud.ps1`. It checks PostgreSQL/schema and performs a tiny Storage upload/delete sentinel. Preflight must show `backend=postgres`, valid schema and no required failures.

## 3. GitHub secrets

Repository → Settings → Secrets and variables → Actions:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Do not add OpenAI secrets until AI is intentionally enabled.

## 4. Manual workflow verification

Run manually once:

- Market ingestion;
- VIRA semantic ingestion;
- Slow-moving macro context;
- Daily risk brief.

Check Supabase table counts/source runs after each.

## 5. Scheduled workflows

The scheduled ingestion jobs intentionally do not rerun pytest. CI performs tests when code changes, reducing GitHub Actions usage.

Market sources poll every 30 minutes during the monitoring window; VIRA is polled during its morning publication window; macro context runs once per weekday.

## 6. Streamlit Community Cloud

Deploy the repository with entry point:

```text
app/Home.py
```

In App Settings → Secrets add values based on `.streamlit/secrets.toml.example`. For the public dashboard, provide `DATABASE_URL` and only optional AI settings. **Do not copy `SUPABASE_SERVICE_ROLE_KEY` into Streamlit**; it belongs only in local admin/bootstrap and GitHub ingestion.

Never put real secrets into the repository.

## 7. Optional OpenAI

Only after deterministic cloud ingestion works:

```text
AI_ENABLED=1
OPENAI_API_KEY=...
```

Use `gpt-5.6-luna` by default for the cost-sensitive enrichment tasks in this project. Keep the daily call cap and output-token caps enabled. Pricing variables can remain zero if you only want token logging.

## 8. Release verification

- `python -m src.system.preflight`
- GitHub CI green.
- Latest source runs visible in Streamlit.
- Daily brief downloadable.
- Historical Replay distinguishes modes.
- AI Usage page works with AI disabled.
- No secrets appear in repository/history/screenshots.

## 9. Enable schedules only after manual verification

Scheduled jobs are guarded by repository variable `AUTOMATION_ENABLED`. Until it equals `1`, scheduled events are skipped while manual `workflow_dispatch` remains usable.

After CI, Cloud verify, Live parser smoke and all ingestion workflows succeed manually:

1. Repository → Settings → Secrets and variables → Actions → Variables.
2. Create `AUTOMATION_ENABLED` with value `1`.
3. Observe at least one scheduled run before treating the deployment as always-on.
