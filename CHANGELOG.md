# Changelog

## v1.0.0-rc3.6 — neutral project wording

- Removed bank-specific references from UI, README and documentation.
- Replaced application-specific presentation notes with a neutral project overview.
- Simplified wording to make the repository read like a standalone technical project.
- No changes to ingestion, signal, storage or replay logic.

## v1.0.0-rc3.5 — live idempotency + CBIS alert de-noising

- Observation identity is now semantic rather than tied to full-page HTML hashes for SBV OMO, VIRA, SBV Macro and HNX aggregate/auction observations. Dynamic banners/timestamps can change raw archives without creating duplicate business observations.
- Raw source hashes remain preserved through content-addressed `raw_object_id`; a genuine value revision still creates a new observation version because value is part of the semantic hash.
- Unclassified `OTHER_MATERIAL_DISCLOSURE` CBIS events remain visible in the event timeline but no longer create LOW alerts by default. Specific payment, extension, collateral, term and non-mechanical suspension events still alert.
- Added regression tests for idempotency across changed raw-page hashes.

## v1.0.0-rc3.4 — live HNX/VIRA parser compatibility

- Updated HNX Government Bond auction parser for the Sep-2026 public schema: `Ngày TCPH`, `Phương thức phát hành`, additional-issuance fields, nominal coupon and registered-yield range.
- Kept `Ngày phát hành` distinct from the auction/organisation date; no date substitution by guess.
- Fixed VIRA latest-article discovery so category pages are never parsed as articles.
- Added dedicated daily/weekly listing fallback when the combined bulletin page does not surface both article families.
- Added regression fixtures for the current HNX auction schema and VIRA category-link collision.

## v1.0.0-rc3.3 — PowerShell encoding hotfix

- Saved all `.ps1` scripts as UTF-8 with BOM for Windows PowerShell 5.1 compatibility.
- Kept PowerShell console messages ASCII-only; Streamlit UI remains Vietnamese-first.


## v1.0.0-rc3.3.1 — Vietnamese UI + live-source hardening
- Vietnamese-first Streamlit UI with English technical terms retained where useful.
- Strict separation between `demo.db` and live `surveillance.db` / PostgreSQL.
- Explicit DEMO/LIVE banner to prevent fixture/live confusion.
- Windows/system TLS trust support for HNX via `truststore`; certificate verification remains enabled.
- CBIS retries, browser-like session warm-up and clearer timeout/TLS diagnostics.
- VIRA publication timestamp parser now accepts both `HH:MM DD/MM/YYYY` and `DD/MM/YYYY HH:MM`, checks metadata, and uses conservative first-observed fallback flagged as inferred.

## v1.0.0-rc2 — Go-live candidate

- added idempotent PostgreSQL/Supabase bootstrap command and Windows helper;
- added live cloud DB/Storage verification with optional sentinel write/delete;
- added non-destructive public-source reachability smoke test;
- added one-command Windows `go_live_gate.ps1`;
- added manual GitHub Actions `Cloud verify` workflow;
- disabled Psycopg auto-prepared statements for Supabase pooler compatibility;
- changed optional AI default to cost-sensitive `gpt-5.6-luna`;
- expanded release regression suite to 53 tests;
- added live non-destructive parser smoke and manual GitHub parser-smoke workflow;
- scheduled cron workflows are OFF by default until `AUTOMATION_ENABLED=1`;
- separated Streamlit secrets from ingestion service-role credentials;
- added `docs/GO_LIVE.md` and clear stable-v1.0.0 acceptance criteria.

## v1.0.0-rc1 — Release candidate

- consolidated SBV OMO, HNX government bonds, HNX CBIS, VIRA and slow-moving SBV macro context;
- deterministic cross-market signals, investigation and point-in-time replay;
- Daily Risk Brief and optional OpenAI enrichment;
- SQLite local / PostgreSQL-Supabase cloud storage;
- GitHub Actions automation and Windows runbook;
- production guards for persistent DB/raw storage and isolated source failures.