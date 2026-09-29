from __future__ import annotations

import pandas as pd


HISTORICAL_VAR_MIN_SESSIONS = 250
MONITORING_MIN_SESSIONS = 60


def history_readiness(store, *, limit: int = 10000) -> pd.DataFrame:
    rows = store.recent_observations(limit=limit)
    if not rows:
        return pd.DataFrame(columns=["risk_factor", "sessions", "monitoring_ready", "historical_var_ready"])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["risk_factor", "sessions", "monitoring_ready", "historical_var_ready"])

    specs = [
        ("USD/VND interbank", "VIRA.FX.INTERBANK", None),
        ("TPCP 5Y", None, "GOV_TENOR:5Y"),
        ("TPCP 10Y", None, "GOV_TENOR:10Y"),
        ("TPCP 15Y", None, "GOV_TENOR:15Y"),
        ("VND O/N", "VIRA.IBOR.RATE", "IBOR:VND:ON"),
    ]
    out = []
    for label, metric, entity in specs:
        sub = df.copy()
        if metric is not None:
            sub = sub[sub["metric_id"].astype(str).eq(metric)]
        else:
            sub = sub[sub["metric_id"].astype(str).isin(["HNX.GOV.TENOR_YIELD", "VIRA.GOV.YIELD"])]
        if entity is not None:
            sub = sub[sub["entity_id"].astype(str).eq(entity)]
        sessions = int(sub["period_end"].astype(str).nunique()) if not sub.empty else 0
        out.append({
            "risk_factor": label,
            "sessions": sessions,
            "monitoring_ready": sessions >= MONITORING_MIN_SESSIONS,
            "historical_var_ready": sessions >= HISTORICAL_VAR_MIN_SESSIONS,
            "minimum_for_var": HISTORICAL_VAR_MIN_SESSIONS,
        })
    return pd.DataFrame(out)
