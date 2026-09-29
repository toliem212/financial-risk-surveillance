# Methodology

## 1. Observation semantics

Every number is classified by economic meaning before it is merged or analysed.

- `FLOW` — additive over a period (for example OMO amount awarded).
- `STOCK` — amount outstanding at a point/end of period.
- `SNAPSHOT` — market/reference value at a point in time.
- `AVERAGE` / `INDEX` — used where source definition requires.

This prevents weekly flow data from being incorrectly treated as a Friday daily observation.

## 2. VIRA daily/weekly handling

Weekly observations are decomposed metric by metric:

- FX / IBOR / TPCP end-of-week values → `DIRECT_WEEKLY_EOP`;
- OMO tender/win/maturity/net → `WEEKLY_AGGREGATE`;
- OMO outstanding/rate → end-of-week stock/snapshot.

A Friday residual can only be derived for an additive flow when Monday–Thursday direct observations are complete, the Monday–Friday week is unambiguous and no direct Friday observation exists. Derived residuals receive lower provenance quality than direct source observations.

## 3. Government-bond curve

Trade-level public HNX YTM observations may be aggregated by canonical tenor to produce a **derived public-trade tenor curve**. This must not be labelled as the official HNX commercial yield-curve product.

## 4. Corporate-bond events

The event layer separates ordinary lifecycle events from risk alerts. For example, a trading suspension explicitly caused by a routine buyback can remain an informational timeline event rather than automatically becoming a high-severity alert.

Rating observations remain on their original agency scales unless an explicit cross-agency mapping methodology is introduced.

## 5. Signal engine

Current MVP signals are deterministic/rule-based. Thresholds in `config/thresholds.json` are illustrative surveillance thresholds, not internal limits of any bank.

The system distinguishes:

```text
Observation → Derived Metric → Signal → Interpretation
```

A signal is not treated as a fact about causality or about a bank's exposure.

## 6. Reconciliation

Secondary/enrichment sources can be reconciled against primary sources. A mismatch creates explicit data-quality status/signal; the system does not silently overwrite the primary source.

## 7. Historical Replay

`SYSTEM_KNOWN` is strict no-hindsight replay based on when this pipeline actually knew the record.

`SOURCE_AVAILABLE` is a research reconstruction that can use source-publication timestamps on later backfills. The UI keeps the two modes separate.

## 8. Macro context

M2, credit and LDR are slow-moving contextual indicators. SBV pages may provide a reference month without a reliable publication timestamp. The project therefore preserves `first_observed_at` rather than inventing an official vintage.

## 9. AI

OpenAI enrichment is optional and downstream of deterministic logic. It must not fabricate missing market data or override authoritative records without validation. AI output is cached/logged and subject to explicit budget controls.
