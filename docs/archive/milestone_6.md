# Milestone 6 — Historical Replay / Point-in-Time Reconstruction

Milestone 6 adds a replay layer without changing source ingestion.

## Two knowledge modes

### SYSTEM_KNOWN (default)
A record is eligible only if the project's own pipeline had observed/fetched it by the replay cutoff. This is the strictest no-hindsight view.

### SOURCE_AVAILABLE
A record is eligible if the public source had published it by the cutoff, even when this project ingested it later during a historical backfill. This mode is useful for research reconstruction but must not be presented as what the running system actually knew.

## Reconstructed vs recorded signals

Replay re-runs deterministic OMO, government-bond and corporate-bond event rules against only eligible point-in-time data. These outputs are labelled reconstructed signals.

Stored `risk_signal` rows are also shown separately as recorded signals. A reconstructed signal is not evidence that the application historically emitted an alert unless a matching recorded signal exists.

## Known limitation

`bond_master` currently stores the latest master state rather than a slowly-changing point-in-time history. Therefore Historical Replay uses corporate-bond events, not current bond-master fields, for historical event state. A versioned/SCD bond-master table is a later extension.
