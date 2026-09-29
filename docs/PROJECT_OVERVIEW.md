# Project Overview

## Purpose

**Vietnam Financial Risk Surveillance System** is an automated point-in-time monitoring system for public data across Vietnam's money, FX and fixed-income markets.

The system is designed to answer five practical questions:

1. What changed?
2. Is the change unusual or material?
3. Which source and data point support the signal?
4. What related market indicators should be checked next?
5. What did the system actually know at that point in time?

## Main workflow

```text
Public sources
    -> ingestion
    -> raw archive
    -> parsing and normalization
    -> validation and reconciliation
    -> observations / bond events
    -> deterministic signals
    -> Risk Feed / Investigation / Historical Replay / Daily Brief
```

## Main modules

- Money market and OMO
- FX pressure
- Government bond and rates monitoring
- Corporate bond event monitoring
- Slow-moving macro context
- Data-quality monitoring
- Historical replay

## Demonstration flow

A short demonstration can follow this order:

1. **System Health** — source status, freshness and errors.
2. **Risk Feed** — recent deterministic signals and material events.
3. **Investigation** — source evidence, data quality and related observations.
4. **Historical Replay** — point-in-time reconstruction without hindsight.
5. **Corporate Bond Event Radar** — event timeline and alert separation.
6. **Daily Risk Brief** — deterministic daily summary.

## Scope boundary

The system uses public data only. It does not contain or infer any institution's internal positions, limits, P&L, liquidity ratios or proprietary exposures.

Thresholds in the repository are illustrative monitoring thresholds and can be adjusted in `config/thresholds.json`.
