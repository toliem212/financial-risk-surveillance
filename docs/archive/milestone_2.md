# Milestone 2 — Cloud-ready persistence and minimal live UI

## Goal

Move persistence off the laptop while keeping local development possible.

## Architecture

SBV OMO -> GitHub Actions -> validation/signals -> Supabase PostgreSQL -> Streamlit
                                  \\-> Supabase Storage (raw HTML, optional)

## Required Supabase setup

1. Create a Supabase project.
2. Open SQL Editor and run `schema/postgres.sql`.
3. Create a private Storage bucket named `raw-market-data`.
4. In **Connect**, copy a PostgreSQL connection string. For this short-lived GitHub worker, the Session Pooler is a simple default; paste the exact Supabase-generated string rather than constructing it manually.
5. Add GitHub repository secrets:
   - `DATABASE_URL`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
6. Add the same `DATABASE_URL` to Streamlit secrets/environment.

## Local development

If `DATABASE_URL` is blank, the project automatically uses SQLite.

```bash
pytest -q
python -m src.jobs.sbv_omo_once --fixture tests/fixtures/sbv_omo_sample.html
streamlit run app/Home.py
```

## Scheduler

`.github/workflows/sbv_omo.yml` checks SBV every 15 minutes on weekdays between 08:00 and 17:59 Asia/Bangkok-equivalent UTC hours.

This is polling, not a claim of exchange-grade real-time data.

## Raw archive

When Supabase Storage credentials are configured, HTML is written to a content-addressed path:

`sbv_omo/YYYY-MM-DD/<sha256>.html`

The same payload therefore does not need a second logical object.

## Security

Never commit database passwords, the Supabase service-role key, or future OpenAI API keys to Git.
