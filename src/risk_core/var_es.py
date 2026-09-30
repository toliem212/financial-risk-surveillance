from __future__ import annotations

from statistics import NormalDist

import pandas as pd


HISTORICAL_VAR_INDICATIVE_MIN_OBS = 200
HISTORICAL_VAR_READY_MIN_OBS = 250
BACKTEST_WINDOW = 250
RATE_DQ_MAX_ABS_BP = 100.0


def _clean_numeric(values) -> pd.Series:
    s = pd.Series(values, dtype="float64") if not isinstance(values, pd.Series) else pd.to_numeric(values, errors="coerce")
    return s.replace([float("inf"), float("-inf")], pd.NA).dropna().astype(float)


def simple_returns(levels: pd.Series) -> pd.Series:
    s = pd.to_numeric(levels, errors="coerce").dropna().astype(float)
    return s.pct_change(fill_method=None).replace([float("inf"), float("-inf")], pd.NA).dropna().astype(float)


def yield_changes_bp(yields_pct: pd.Series) -> pd.Series:
    s = pd.to_numeric(yields_pct, errors="coerce").dropna().astype(float)
    return (s.diff() * 100.0).dropna()


def historical_var_from_pnl(pnl, confidence: float = 0.99) -> float | None:
    series = _clean_numeric(pnl)
    if series.empty:
        return None
    losses = -series
    return max(0.0, float(losses.quantile(confidence, interpolation="linear")))


def expected_shortfall_from_pnl(pnl, confidence: float = 0.975) -> float | None:
    series = _clean_numeric(pnl)
    if series.empty:
        return None
    losses = -series
    threshold = float(losses.quantile(confidence, interpolation="linear"))
    tail = losses[losses >= threshold]
    if tail.empty:
        return None
    return max(0.0, float(tail.mean()))


def parametric_var_from_pnl(pnl, confidence: float = 0.99) -> float | None:
    series = _clean_numeric(pnl)
    if len(series) < 2:
        return None
    mu = float(series.mean())
    sigma = float(series.std(ddof=1))
    z = NormalDist().inv_cdf(confidence)
    return max(0.0, -mu + z * sigma)


def rate_portfolio_pnl_bn(yield_changes: pd.DataFrame, pv01_bn_per_bp: dict[str, float]) -> pd.Series:
    required = [c for c in pv01_bn_per_bp if c in yield_changes.columns]
    if not required:
        return pd.Series(dtype="float64", name="rates_pnl_bn_vnd")
    frame = yield_changes[required].apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if frame.empty:
        return pd.Series(dtype="float64", name="rates_pnl_bn_vnd")
    pnl = pd.Series(0.0, index=frame.index, dtype="float64")
    for tenor in required:
        pnl = pnl - frame[tenor] * float(pv01_bn_per_bp[tenor])
    pnl.name = "rates_pnl_bn_vnd"
    return pnl


def fx_position_pnl_bn(fx_returns: pd.Series, position_mn_ccy: float, current_spot_vnd_per_ccy: float) -> pd.Series:
    r = pd.to_numeric(fx_returns, errors="coerce").dropna().astype(float)
    pnl = float(position_mn_ccy) * float(current_spot_vnd_per_ccy) * r / 1000.0
    pnl.name = "fx_pnl_bn_vnd"
    return pnl


def rolling_historical_var_backtest(
    pnl,
    *,
    confidence: float = 0.99,
    window: int = BACKTEST_WINDOW,
) -> dict:
    series = _clean_numeric(pnl).reset_index(drop=True)
    if len(series) <= window:
        return {
            "window": window,
            "observations": 0,
            "exceptions": 0,
            "exception_rate_pct": None,
            "expected_exception_rate_pct": (1.0 - confidence) * 100.0,
        }

    exceptions = 0
    observations = 0
    for i in range(window, len(series)):
        var = historical_var_from_pnl(series.iloc[i - window : i], confidence=confidence)
        if var is None:
            continue
        realized_loss = -float(series.iloc[i])
        observations += 1
        if realized_loss > var:
            exceptions += 1

    return {
        "window": window,
        "observations": observations,
        "exceptions": exceptions,
        "exception_rate_pct": (exceptions / observations * 100.0) if observations else None,
        "expected_exception_rate_pct": (1.0 - confidence) * 100.0,
    }


def _dedupe_observations(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    if "fetched_at" not in df.columns:
        df["fetched_at"] = ""
    df["_fetched"] = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce")
    df["_period"] = pd.to_datetime(df["period_end"], errors="coerce")
    df = df.dropna(subset=["_period"])
    df = df.sort_values(["_period", "_fetched"])
    return df.drop_duplicates(["metric_id", "entity_id", "period_end"], keep="last")


def _rates_history(df: pd.DataFrame, snapshot: dict) -> tuple[dict, pd.Series]:
    if df.empty:
        return _not_ready_scope("Rates / TPCP", 0, 0), pd.Series(dtype="float64")

    sub = df[
        df["metric_id"].astype(str).eq("HNX.GOV.TENOR_YIELD")
        & df["entity_id"].astype(str).isin(["GOV_TENOR:5Y", "GOV_TENOR:10Y", "GOV_TENOR:15Y"])
    ].copy()
    if sub.empty:
        return _not_ready_scope("Rates / TPCP", 0, 0), pd.Series(dtype="float64")

    sub["tenor"] = sub["entity_id"].astype(str).str.replace("GOV_TENOR:", "", regex=False)
    sub["value"] = pd.to_numeric(sub["value"], errors="coerce")
    levels = sub.pivot_table(index="_period", columns="tenor", values="value", aggfunc="last").sort_index()
    available = [c for c in ("5Y", "10Y", "15Y") if c in levels.columns]
    if not available:
        return _not_ready_scope("Rates / TPCP", int(len(levels)), 0), pd.Series(dtype="float64")

    changes = levels[available].diff() * 100.0
    complete = changes.dropna(how="any")
    if complete.empty:
        return _not_ready_scope("Rates / TPCP", int(len(levels)), 0), pd.Series(dtype="float64")

    dq_mask = complete.abs().le(RATE_DQ_MAX_ABS_BP).all(axis=1)
    dq_excluded = int((~dq_mask).sum())
    clean_changes = complete[dq_mask]

    bonds = snapshot.get("bond_positions")
    pv01_map: dict[str, float] = {}
    if isinstance(bonds, pd.DataFrame) and not bonds.empty:
        for _, row in bonds.iterrows():
            tenor = str(row.get("bond_bucket"))
            if tenor in available and pd.notna(row.get("pv01_bn_per_bp")):
                pv01_map[tenor] = float(row["pv01_bn_per_bp"])

    pnl = rate_portfolio_pnl_bn(clean_changes, pv01_map)
    return _scope_report("Rates / TPCP", pnl, sessions=int(len(levels)), dq_excluded=dq_excluded), pnl


def _fx_history(df: pd.DataFrame, snapshot: dict) -> tuple[dict, pd.Series]:
    if df.empty:
        return _not_ready_scope("FX / USD-VND", 0, 0), pd.Series(dtype="float64")

    sub = df[df["metric_id"].astype(str).eq("VIRA.FX.INTERBANK")].copy()
    if sub.empty:
        return _not_ready_scope("FX / USD-VND", 0, 0), pd.Series(dtype="float64")

    sub["value"] = pd.to_numeric(sub["value"], errors="coerce")
    levels = sub.dropna(subset=["value"]).sort_values("_period").set_index("_period")["value"]
    levels = levels[~levels.index.duplicated(keep="last")]
    returns = simple_returns(levels)

    spot = snapshot.get("market", {}).get("fx_usd_vnd", {}).get("spot")
    position = snapshot.get("usd_nop_mn")
    if spot is None or position is None:
        return _not_ready_scope("FX / USD-VND", int(len(levels)), 0), pd.Series(dtype="float64")

    pnl = fx_position_pnl_bn(returns, float(position), float(spot))
    return _scope_report("FX / USD-VND", pnl, sessions=int(len(levels)), dq_excluded=0), pnl


def _not_ready_scope(name: str, sessions: int, pnl_observations: int, dq_excluded: int = 0) -> dict:
    return {
        "risk_scope": name,
        "sessions": sessions,
        "pnl_observations": pnl_observations,
        "minimum_required": HISTORICAL_VAR_READY_MIN_OBS,
        "status": "NOT_READY",
        "historical_var_99_bn": None,
        "expected_shortfall_97_5_bn": None,
        "expected_shortfall_99_bn": None,
        "parametric_var_99_bn": None,
        "dq_excluded": dq_excluded,
        "backtest_observations": 0,
        "backtest_exceptions": 0,
        "backtest_exception_rate_pct": None,
    }


def _scope_report(name: str, pnl: pd.Series, *, sessions: int, dq_excluded: int) -> dict:
    clean = _clean_numeric(pnl)
    if len(clean) < HISTORICAL_VAR_INDICATIVE_MIN_OBS:
        return _not_ready_scope(name, sessions, int(len(clean)), dq_excluded=dq_excluded)

    status = "READY" if len(clean) >= HISTORICAL_VAR_READY_MIN_OBS else "INDICATIVE"
    backtest = rolling_historical_var_backtest(clean, confidence=0.99, window=BACKTEST_WINDOW)
    return {
        "risk_scope": name,
        "sessions": sessions,
        "pnl_observations": int(len(clean)),
        "minimum_required": HISTORICAL_VAR_READY_MIN_OBS,
        "status": status,
        "historical_var_99_bn": historical_var_from_pnl(clean, confidence=0.99),
        "expected_shortfall_97_5_bn": expected_shortfall_from_pnl(clean, confidence=0.975),
        "expected_shortfall_99_bn": expected_shortfall_from_pnl(clean, confidence=0.99),
        "parametric_var_99_bn": parametric_var_from_pnl(clean, confidence=0.99),
        "dq_excluded": dq_excluded,
        "backtest_observations": int(backtest["observations"]),
        "backtest_exceptions": int(backtest["exceptions"]),
        "backtest_exception_rate_pct": backtest["exception_rate_pct"],
    }


def build_var_es_report(store, snapshot: dict, *, limit: int = 100000) -> pd.DataFrame:
    rows = store.recent_observations(limit=limit)
    df = _dedupe_observations(rows)

    rates, rates_pnl = _rates_history(df, snapshot)
    fx, fx_pnl = _fx_history(df, snapshot)

    combined = _not_ready_scope("Combined market risk", 0, 0)
    if not rates_pnl.empty and not fx_pnl.empty:
        aligned = pd.concat([rates_pnl, fx_pnl], axis=1, join="inner").dropna(how="any")
        if not aligned.empty:
            combined_pnl = aligned.sum(axis=1)
            combined = _scope_report(
                "Combined market risk",
                combined_pnl,
                sessions=int(len(aligned) + 1),
                dq_excluded=0,
            )

    return pd.DataFrame([rates, fx, combined])
