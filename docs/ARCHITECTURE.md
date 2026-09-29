# Architecture

## Product boundary

The system monitors the **external public-market environment**. It does not model a bank's internal positions, limits or P&L.

## Pipeline

```text
Public Sources
  ├─ SBV OMO
  ├─ SBV M2 / Credit / LDR
  ├─ HNX Government Bonds
  ├─ HNX CBIS
  └─ VIRA
       ↓
Ingestion Workers
       ↓
Raw Archive (content-addressed, append-only)
       ↓
Parser / Normalization
       ↓
Validation + Reconciliation
       ↓
PostgreSQL/SQLite
  ├─ market_observation
  ├─ source_run
  ├─ risk_signal
  ├─ issuer_master
  ├─ bond_master
  ├─ bond_event
  ├─ ai_cache
  ├─ ai_usage_log
  └─ project_meta
       ↓
Deterministic Signal Engine
       ↓
Risk Feed / Investigation / Replay / Brief
       ↓
Optional OpenAI Enrichment
```

## Storage modes

### Local

- SQLite for normalized/event/signal data.
- filesystem for raw HTML.

### Cloud

- Supabase PostgreSQL for database state.
- optional private Supabase Storage bucket for raw HTML.

The business logic uses a common store contract so ingestion/risk code does not need separate local/cloud implementations.

## Idempotency

Observations and events carry stable hashes/business keys. Re-running a worker against identical source content should not produce duplicate observations/events.

## Point-in-time model

The system separates:

- economic/reference period;
- source publication time when known;
- first observation by this system;
- fetch time;
- processing time.

Historical Replay uses these timestamps to avoid hindsight.

## AI boundary

AI sits after the deterministic system. It can classify ambiguous disclosure text or explain an already-computed signal, but it does not calculate VaR/PV01, market returns, z-scores or rule thresholds and does not replace authoritative observations.
