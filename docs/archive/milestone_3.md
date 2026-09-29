# Milestone 3 — HNX Government Bond Surveillance

## Delivered

- Public HNX outright-trade ingestion adapter.
- Public HNX auction-result ingestion adapter.
- Robust HNX HTML table parser with numeric and tenor normalization.
- Trade-level YTM observations with source-quality `A`.
- Derived tenor-bucket yield observations with quality `B`.
- Tenor turnover and trade-count observations.
- Public auction offered/bid/awarded value and auction-yield observations where fields are available.
- Rates signal engine:
  - `YIELD_MOVE_HIGH`
  - `CURVE_STEEPENING`
  - `CURVE_FLATTENING`
- Dashboard government-bond section.
- Combined scheduled workflow for SBV + HNX to reduce repeated GitHub runner startup cost.
- Offline fixtures and regression tests.

## Methodological guardrail

`HNX.GOV.TENOR_YIELD` is a **derived public-trade tenor curve** built from HNX public outright trades. It must not be presented as the official HNX yield curve. The official HNX EOD/yield-curve information products may have separate commercial access terms.

## Current limitation

Live HNX integration could not be executed from the build container because DNS resolution is blocked in this environment. The HNX public pages/endpoints were separately checked on the web, while parser/integration behaviour is covered with fixed regression fixtures.

## Next milestone

HNX CBIS Corporate Bond Event Radar:

- issuer/bond identity;
- lifecycle events;
- buybacks;
- ratings;
- disclosures;
- trading-status events;
- event-sourced outstanding;
- deterministic event alerts.
