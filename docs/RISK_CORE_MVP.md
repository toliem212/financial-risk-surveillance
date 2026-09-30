# Market & Liquidity Risk Core — MVP

This layer turns the public-data surveillance pipeline into a banking risk-control simulation.

## Design principle

- **Market factors:** public observations already collected from SBV, HNX, VIRA and CBIS.
- **Bank exposures and limits:** deliberately **synthetic** and version-controlled under `config/risk_book/`.
- Synthetic values are never presented as data from a real bank.
- Missing market data remains `N/A`; the engine does not replace missing observations with zero.

## MVP calculations

### FX

- USD net open position (NOP): signed sum of synthetic USD positions.
- Linear stress P&L: `NOP × spot × shock%`.
- Positive USD/VND shock means USD appreciates versus VND; a short USD position therefore loses.

### Government bonds / rates

- Approximate PV01: `Market Value × Modified Duration × 0.0001`.
- Approximate P&L for a yield move: `-PV01 × Δyield(bp)`.
- Parallel rate stress is intentionally simple in this MVP.
- This is sensitivity-based approximation, not full cash-flow valuation of a specific bond.

### Liquidity

- Contractual gap by time bucket: `inflows - outflows`.
- Cumulative gap is the running sum across buckets.
- Stress applies an additional outflow percentage to the selected horizon.
- O/N interbank rates and OMO are market-liquidity context, not substitutes for internal cash-flow data.

### Limits / EWS

- `NORMAL`: utilization < 80%
- `WATCH`: 80% to < 90%
- `WARNING`: 90% to 100%
- `BREACH`: > 100%

These thresholds are portfolio simulation rules, not the internal limits of any named institution.

## Historical VaR / ES readiness

The dashboard reports data coverage rather than fabricating a VaR estimate from a short history.

- 60 sessions: minimum monitoring-history flag.
- 250 sessions: minimum sample gate before Historical VaR / ES is enabled in a later milestone.

The next milestone is historical backfill and point-in-time return/yield-change series, followed by Historical VaR, parametric VaR, ES and backtesting.

## Quant VaR / ES layer

The deterministic quant layer implements:

- simple returns for FX market levels;
- daily government-bond yield changes in basis points;
- sensitivity-based historical rate P&L using current synthetic PV01 by tenor;
- Historical VaR at 99%;
- Expected Shortfall at 97.5% and 99%;
- Parametric/Normal VaR at 99%;
- rolling Historical VaR backtesting with a 250-observation estimation window.

Project governance for the prototype:

- READY: at least 250 valid historical P&L observations;
- INDICATIVE: 200-249 valid historical P&L observations;
- NOT_READY: fewer than 200 valid historical P&L observations.

The 200-observation INDICATIVE gate is an internal prototype convention, not a regulatory
minimum or an industry requirement. Backtesting is not shortened to fit the available sample.
Rate moves exceeding the MVP data-quality threshold are excluded from the VaR sample and counted
as DQ exclusions rather than silently winsorized or replaced. No synthetic market history is created.
