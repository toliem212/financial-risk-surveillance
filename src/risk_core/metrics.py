from __future__ import annotations

import math

import pandas as pd


LIMIT_WATCH_PCT = 80.0
LIMIT_WARNING_PCT = 90.0
LIMIT_BREACH_PCT = 100.0


def limit_utilization(current_value: float | None, limit_value: float | None, *, absolute: bool = True) -> float | None:
    if current_value is None or limit_value is None or not math.isfinite(float(limit_value)) or float(limit_value) <= 0:
        return None
    current = float(current_value)
    if absolute:
        current = abs(current)
    return current / float(limit_value) * 100.0


def limit_status(utilization_pct: float | None) -> str:
    if utilization_pct is None or not math.isfinite(float(utilization_pct)):
        return "NOT_AVAILABLE"
    u = float(utilization_pct)
    if u > LIMIT_BREACH_PCT:
        return "BREACH"
    if u >= LIMIT_WARNING_PCT:
        return "WARNING"
    if u >= LIMIT_WATCH_PCT:
        return "WATCH"
    return "NORMAL"


def fx_nop_mn(positions: pd.DataFrame, currency: str = "USD") -> float:
    subset = positions[positions["currency"].astype(str).str.upper().eq(currency.upper())]
    return float(pd.to_numeric(subset["position_mn_ccy"], errors="coerce").fillna(0).sum())


def fx_stress_pnl_bn_vnd(position_mn_ccy: float, spot_vnd_per_ccy: float | None, shock_pct: float) -> float | None:
    """Linear FX P&L in VND bn for a signed foreign-currency position.

    Positive position = long foreign currency. Positive shock = foreign currency
    appreciates versus VND. A short USD position therefore loses when USD/VND rises.
    """
    if spot_vnd_per_ccy is None:
        return None
    return float(position_mn_ccy) * float(spot_vnd_per_ccy) * (float(shock_pct) / 100.0) / 1000.0


def bond_pv01_bn(market_value_bn_vnd: float, modified_duration: float, position_sign: float = 1.0) -> float:
    """Signed PV01 in VND bn per 1 bp yield decline.

    For a long bond, the magnitude is MV * ModDuration * 1bp. The engine reports
    PV01 magnitude separately for limits and uses sign when translating yield moves
    into approximate P&L.
    """
    return float(position_sign) * float(market_value_bn_vnd) * float(modified_duration) * 0.0001


def bond_pnl_from_yield_move_bn(pv01_bn: float, yield_change_bp: float | None) -> float | None:
    if yield_change_bp is None:
        return None
    return -float(pv01_bn) * float(yield_change_bp)


def liquidity_gap_table(gaps: pd.DataFrame) -> pd.DataFrame:
    out = gaps.copy().sort_values("bucket_order").reset_index(drop=True)
    out["inflows_bn_vnd"] = pd.to_numeric(out["inflows_bn_vnd"], errors="coerce").fillna(0.0)
    out["outflows_bn_vnd"] = pd.to_numeric(out["outflows_bn_vnd"], errors="coerce").fillna(0.0)
    out["net_gap_bn_vnd"] = out["inflows_bn_vnd"] - out["outflows_bn_vnd"]
    out["cumulative_gap_bn_vnd"] = out["net_gap_bn_vnd"].cumsum()
    return out


def liquidity_stress_gap_bn(gaps: pd.DataFrame, *, through_bucket_order: int, outflow_addon_pct: float) -> float:
    base = liquidity_gap_table(gaps)
    window = base[base["bucket_order"] <= int(through_bucket_order)]
    inflows = float(window["inflows_bn_vnd"].sum())
    outflows = float(window["outflows_bn_vnd"].sum())
    stressed_outflows = outflows * (1.0 + float(outflow_addon_pct) / 100.0)
    return inflows - stressed_outflows
