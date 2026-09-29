# Milestone 4 — HNX CBIS Corporate Bond Event Radar

## Goal

Add an auditable corporate-bond event layer without relying on an LLM for primary classification.

## Public CBIS surfaces used

- Issuer list
- Registered bond list
- Rating information
- Issuer disclosures
- Trading-registration/status disclosures

## Data model change

Milestone 4 adds `bond_master` to the original five-table MVP. Corporate-bond identity and registration state are master data and should not be forced into `market_observation`.

## Event taxonomy

- REGISTRATION
- TRADING_SUSPENSION
- DELISTING
- BUYBACK
- PAYMENT_EVENT
- PAYMENT_DELAY
- MATURITY_EXTENSION
- TERM_CHANGE
- COLLATERAL_CHANGE
- RATING_OBSERVATION
- OTHER_MATERIAL_DISCLOSURE

## Alerting rule

Events are not equivalent to alerts. Routine lifecycle events remain visible in the event timeline, while higher-attention events create `risk_signal` rows.

A trading suspension caused by a disclosed buyback is informational by default; it is not automatically treated as stress.

## Rating guardrail

Ratings are stored with agency and scale. No cross-agency ranking or numeric conversion is performed in the MVP.

## Limitation

The HTML implementation is optimized for continuous detection of current public records. Exhaustive historical pagination/backfill and attachment-level extraction remain future work.
