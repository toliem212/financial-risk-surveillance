# Release Status — v1.0.0-rc3.6

## Offline release gate completed

- **64/64 pytest tests passed**.
- `python -m compileall -q src app` passed.
- Offline end-to-end `src.system.release_check` passed.
- Fixture E2E produces all core data domains, signals, CBIS events and a deterministic Daily Risk Brief.
- Cloud bootstrap and cloud verification commands are implemented with explicit opt-in/write-test behavior.
- Live fetch+parse smoke exists and writes no surveillance data.
- Scheduled GitHub jobs are disabled until repository variable `AUTOMATION_ENABLED=1`.
- Postgres adapter disables Psycopg auto-prepared statements for Supabase pooler compatibility.
- Default optional AI model is `gpt-5.6-luna`; AI remains OFF by default.

## External validation still required on the user's account/network

The packaging environment does not have the user's credentials and cannot be used to claim successful deployment of:

- live SBV/HNX/CBIS/VIRA parser integration from the user's network;
- real Supabase PostgreSQL DDL/bootstrap and Storage write/delete;
- real GitHub Actions secrets and scheduled runs;
- real Streamlit Community Cloud app;
- real paid OpenAI API call.

Use `docs/GO_LIVE.md` and `scripts/go_live_gate.ps1` for those final gates.

## Stable v1.0.0 criterion

Rename rc3.5 to **v1.0.0** only after:

1. local live-source pass is acceptable;
2. `cloud_verify --write-test` succeeds;
3. all GitHub workflows run manually at least once;
4. one scheduled ingestion succeeds while the laptop is off;
5. Streamlit displays the newer cloud data;
6. any optional AI paid call is tested only if AI will be part of the public demo.
