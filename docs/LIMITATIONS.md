# Limitations and Guardrails

1. **Public data are not contracted real-time feeds.** The product is automated near-real-time public-data surveillance.
2. **Source websites can change or block automation.** Failures are logged as source failures and must not be interpreted as zero activity.
3. **HNX derived tenor curve is not the official paid HNX curve.**
4. **CBIS historical backfill is not exhaustive in the near-real-time worker.** Current-event detection is prioritised.
5. **Detailed corporate-bond economic impact may require attached-document review.** Deterministic title/metadata classification has limits.
6. **`bond_master` is latest-state.** Historical Replay uses timestamped events rather than pretending current master state existed historically.
7. **VIRA wording can change.** Ambiguity should lower quality or fail loudly rather than being coerced into a daily time series.
8. **Holiday-aware Friday residual logic is limited.** Strict Monday–Friday conditions are intentionally conservative.
9. **SBV M2/credit/LDR source pages expose only the latest month.** History accumulates only while the worker runs; missed months may remain missing.
10. **Macro publication timestamp may be unavailable.** The project keeps first-observed time instead of inventing a source vintage.
11. **AI is optional and separately billed.** ChatGPT Plus does not include API usage.
12. **No bank-internal data.** Public-market observations do not demonstrate any institution's actual holdings, limits, P&L or risk appetite.
