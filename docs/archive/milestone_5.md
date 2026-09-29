# Milestone 5 — VIRA Daily/Weekly Semantic Normalization

## Objective

Use VIRA as a **secondary/enrichment/cross-check source** without forcing daily and weekly bulletins into one date-row model.

## Semantic rules

- FX, IBOR and government-bond yields in a weekly bulletin are end-of-week observations (`DIRECT_WEEKLY_EOP`).
- OMO tender/win/maturity/net in a weekly bulletin are weekly additive flows (`WEEKLY_AGGREGATE`).
- OMO outstanding is an end-of-week stock (`DIRECT_WEEKLY_EOP`).
- Daily observations remain `DIRECT_DAILY`.
- A Friday OMO residual may be derived only for additive FLOW metrics and only when Monday–Thursday each have one direct daily observation and Friday is not directly observed.
- Ambiguous weeks/holidays are left missing rather than inferred.

## Friday residual

For eligible flow metric `x`:

```text
Friday(x) = WeeklyTotal(x) - Monday(x) - Tuesday(x) - Wednesday(x) - Thursday(x)
```

Derived observations are marked:

```text
observation_method = DERIVED_RESIDUAL
quality_flag = B
```

## Cross-source reconciliation

MVP supports:

- `VIRA.GOV.YIELD` vs `HNX.GOV.TENOR_YIELD`, same tenor/date;
- daily `VIRA.OMO.REPO.WIN` vs the sum of same-day SBV OMO injection volumes.

A match upgrades the VIRA secondary observation from `C` to `B` and stores reconciliation evidence in `dims_json`.

A mismatch keeps the observation for audit, downgrades it to `D`, and emits `SOURCE_MISMATCH` in the `DATA_QUALITY` domain.

## Guardrails

- Weekly flow is never silently treated as a Friday daily flow.
- Stock/snapshot values are never reconstructed by subtraction.
- Publication date and market/reference date remain separate.
- If the market date must fall back to the article date, quality is `D`.
- VIRA remains a secondary source; primary HNX/SBV data are not overwritten by VIRA.
