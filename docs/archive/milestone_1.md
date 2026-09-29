# Milestone 1 — SBV OMO vertical slice

Goal: prove the full data contract before adding more sources.

Flow:

`SBV OMO -> raw HTML -> parser -> canonical observations -> validation -> signal comparison -> local database`

## Five MVP tables

1. `source_run` — operational lineage and failures.
2. `market_observation` — canonical point-in-time numerical observations.
3. `risk_signal` — derived surveillance signals.
4. `issuer_master` — reserved for HNX CBIS Milestone 3.
5. `bond_event` — reserved for HNX CBIS Milestone 3.

Raw source payloads are not a sixth database table. They are append-only objects/files referenced by `raw_object_id`.

## Important semantic choices

- OMO awarded volume is `FLOW`.
- OMO rate is `SNAPSHOT` for that operation/tenor.
- Source is `SBV` and quality is `A` when parsed directly from the official publication.
- `source_published_at` remains null until a reliable publication timestamp is available.
- `first_observed_at` is when our system first fetched the page.
- Repeated fetches are idempotent.

## Next milestone

Replace SQLite storage in scheduled runs with Supabase/PostgreSQL, then deploy a minimal System Health + OMO page in Streamlit.
