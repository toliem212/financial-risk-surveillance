# Release Checklist

## Local

- [ ] Python 3.11+ / Git available.
- [ ] `scripts/setup_windows.ps1` succeeds.
- [ ] `scripts/release_check.ps1` succeeds.
- [ ] Offline demo opens Streamlit.
- [ ] Risk Feed, Daily Brief, AI Usage and Replay pages render.
- [ ] `run_live_once.ps1` records public-source successes/failures visibly.

## Supabase

- [ ] `schema/postgres.sql` applied.
- [ ] `schema/supabase_storage.sql` applied.
- [ ] `DATABASE_URL` connects.
- [ ] private raw bucket exists.
- [ ] production preflight with `--require-postgres --require-cloud-raw` passes.

## GitHub

- [ ] repository secrets configured.
- [ ] CI green.
- [ ] all scheduled workflows manually tested once.
- [ ] no secret appears in Actions logs.

## Streamlit

- [ ] app uses cloud `DATABASE_URL`.
- [ ] Home/System Health shows current source runs.
- [ ] no confidential/service credentials displayed.

## AI (optional)

- [ ] deterministic core works with `AI_ENABLED=0`.
- [ ] API key configured only in secrets.
- [ ] daily call limit and token caps remain enabled.
- [ ] cost/token page is visible.

## Project presentation

- [ ] public-data disclaimer visible.
- [ ] no claim of bank-internal exposure.
- [ ] derived HNX curve labelled as derived public-trade curve.
- [ ] Replay mode distinction explained.
- [ ] 5–7 minute demo path rehearsed.
