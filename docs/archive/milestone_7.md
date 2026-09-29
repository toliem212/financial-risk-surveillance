# Milestone 7 — Cross-Market Risk Feed & Investigation

Milestone 7 turns separate domain signals into one investigation workflow.

## Added

- Deterministic FX signals:
  - `FX_MOVE_HIGH`
  - `FX_POLICY_REFERENCE_PROXIMITY`
- Cross-market Risk Feed combining:
  - Liquidity signals
  - FX signals
  - Government-bond/rates signals
  - Corporate-bond alerts
  - Data-quality signals
  - INFO-only corporate-bond lifecycle events
- Investigation case builder:
  - What changed
  - Evidence
  - Data quality
  - Related public-market observations
  - 60-day historical context when available
  - Possible risk-transmission channels
  - What to monitor next
- Streamlit `Cross-Market Risk Feed & Investigation` page.
- Historical Replay now reconstructs FX signals as well.

## Guardrails

- `FX_POLICY_REFERENCE_PROXIMITY` treats the SBV selling rate only as a published policy/reference level. It is not labelled as an interbank trading ceiling.
- Risk-transmission text describes possible channels and does not claim causality from co-movement alone.
- Public-market signals do not imply that any specific institution holds a position or has direct exposure.
- INFO lifecycle events remain visible without automatically becoming risk alerts.
- AI/OpenAI is still intentionally absent from the deterministic core.

## Test status

Milestone 7 adds regression tests for FX signals, unified Risk Feed, Investigation context, data-quality state and FX point-in-time replay.

## CLI

```bash
python -m src.jobs.risk_feed_snapshot --limit 50
python -m src.jobs.risk_feed_snapshot --signal-id <SIGNAL_ID>
```
