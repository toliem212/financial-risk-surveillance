# Data Dictionary

## `market_observation`

Grain: one metric × entity × period × source/content version.

Key fields:

- `metric_id` — canonical metric identifier.
- `entity_type`, `entity_id` — monitored object.
- `value`, `unit` — numeric observation.
- `period_start`, `period_end` — economic/reference period.
- `as_of_time` — source as-of timestamp where available.
- `measure_type` — `SNAPSHOT`, `FLOW`, `STOCK`, `AVERAGE`, `INDEX`, `EVENT`.
- `frequency` — session/daily/weekly/monthly etc.
- `source`, `source_url` — lineage.
- `source_published_at` — source publication timestamp when known.
- `first_observed_at` — first time this system saw the record.
- `fetched_at`, `processed_at` — pipeline timestamps.
- `observation_method` — direct/weekly-EOP/weekly-aggregate/derived etc.
- `quality_flag` — `A/B/C/D/X`.
- `raw_object_id` — link/reference to archived raw source.
- `parser_version` — parser lineage.
- `record_hash` — **semantic/content-version hash** used for idempotency; it is intentionally independent of full-page HTML hashes so dynamic banners/timestamps do not duplicate the same business observation. A genuine value revision creates a new semantic hash/version.
- `raw_object_id` remains the provenance pointer to the content-addressed raw page/object.
- `dims_json` — source-specific dimensions.

## `source_run`

One ingestion-worker run. Stores status, record counts, error type/message, versions and latest source timestamp.

## `risk_signal`

One deterministic risk/data-quality signal. Stores signal type, domain, entity, generated timestamp, current/baseline/change values, threshold, severity, structured evidence and status.

## `issuer_master`

Latest issuer identity/master data available from public CBIS context.

## `bond_master`

Latest registered-bond identity/master state. It is not used as historical point-in-time state in Replay because it is currently latest-state rather than SCD/versioned.

## `bond_event`

Timestamped corporate-bond lifecycle/risk events such as registration, buyback/payment events, rating observations, maturity extension, collateral/term change, trading suspension and delisting.

## `ai_cache`

Content-addressed cache for optional AI enrichment. Prevents repeated paid calls for identical feature/model/prompt/content combinations.

## `ai_usage_log`

Audit of API/cache usage and token counts. Pricing is supplied by environment variables rather than hard-coded.

## `project_meta`

Small operational metadata table, currently including schema/project version information.

## Core metric namespaces

- `SBV.OMO.*` — direct OMO observations.
- `SBV.MACRO.*` — slow-moving M2/credit/LDR context.
- `HNX.GOV.*` — government-bond trade/auction/derived-tenor observations.
- `VIRA.FX.*` — VIRA FX observations.
- `VIRA.IBOR.*` — VIRA interbank-rate observations.
- `VIRA.GOV.*` — VIRA TPCP observations.
- `VIRA.OMO.*` — VIRA OMO observations with explicit daily/weekly semantics.
