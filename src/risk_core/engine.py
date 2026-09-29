from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.risk_core.loaders import (
    DEFAULT_BOOK_DIR,
    load_bond_positions,
    load_fx_positions,
    load_liquidity_gap,
    load_risk_limits,
    load_stress_scenarios,
)
from src.risk_core.market_inputs import latest_market_inputs
from src.risk_core.metrics import (
    bond_pnl_from_yield_move_bn,
    bond_pv01_bn,
    fx_nop_mn,
    fx_stress_pnl_bn_vnd,
    limit_status,
    limit_utilization,
    liquidity_gap_table,
    liquidity_stress_gap_bn,
)
from src.risk_core.readiness import history_readiness


def _limit_row(limits: pd.DataFrame, metric_id: str):
    hit = limits[limits["metric_id"].astype(str).eq(metric_id)]
    return hit.iloc[0].to_dict() if not hit.empty else None


def _limit_record(limits: pd.DataFrame, metric_id: str, current_value: float | None) -> dict:
    row = _limit_row(limits, metric_id)
    if row is None:
        return {
            "metric_id": metric_id,
            "current_value": current_value,
            "limit_value": None,
            "unit": None,
            "utilization_pct": None,
            "status": "NOT_AVAILABLE",
        }
    util = limit_utilization(current_value, float(row["limit_value"]), absolute=bool(row.get("absolute_value", True)))
    return {
        "metric_id": metric_id,
        "current_value": current_value,
        "limit_value": float(row["limit_value"]),
        "unit": row.get("unit"),
        "utilization_pct": util,
        "status": limit_status(util),
        "description": row.get("description"),
    }


def build_risk_snapshot(store, *, book_dir: Path = DEFAULT_BOOK_DIR) -> dict:
    fx_positions = load_fx_positions(book_dir)
    bond_positions = load_bond_positions(book_dir)
    liquidity = load_liquidity_gap(book_dir)
    limits = load_risk_limits(book_dir)
    scenarios = load_stress_scenarios(book_dir)
    market = latest_market_inputs(store)

    usd_nop = fx_nop_mn(fx_positions, "USD")
    spot = market["fx_usd_vnd"]["spot"]

    fx_stress_rows = []
    for row in scenarios.to_dict("records"):
        pnl = fx_stress_pnl_bn_vnd(usd_nop, spot, float(row["fx_usd_vnd_shock_pct"]))
        fx_stress_rows.append({**row, "fx_pnl_bn_vnd": pnl, "fx_loss_bn_vnd": max(0.0, -pnl) if pnl is not None else None})
    fx_stress = pd.DataFrame(fx_stress_rows)

    bond_rows = []
    for row in bond_positions.to_dict("records"):
        tenor = str(row["bond_bucket"])
        market_row = market["gov_yields"].get(tenor, {})
        pv01 = bond_pv01_bn(float(row["market_value_bn_vnd"]), float(row["modified_duration"]), float(row.get("position_sign", 1)))
        pnl = bond_pnl_from_yield_move_bn(pv01, market_row.get("change_bp"))
        bond_rows.append({
            **row,
            "market_yield_pct": market_row.get("value_pct"),
            "previous_yield_pct": market_row.get("previous_value_pct"),
            "previous_period_end": market_row.get("previous_period_end"),
            "raw_yield_change_bp": market_row.get("raw_change_bp"),
            "yield_change_bp": market_row.get("change_bp"),
            "market_dq_status": market_row.get("dq_status"),
            "market_dq_reason": market_row.get("dq_reason"),
            "market_source": market_row.get("source"),
            "market_quality": market_row.get("quality_flag"),
            "pv01_bn_per_bp": pv01,
            "estimated_market_pnl_bn_vnd": pnl,
        })
    bonds = pd.DataFrame(bond_rows)
    total_pv01 = float(bonds["pv01_bn_per_bp"].abs().sum()) if not bonds.empty else 0.0

    rate_stress_rows = []
    for row in scenarios.to_dict("records"):
        shock = float(row["rates_parallel_bp"])
        pnl = -total_pv01 * shock
        rate_stress_rows.append({**row, "rates_pnl_bn_vnd": pnl, "rates_loss_bn_vnd": max(0.0, -pnl)})
    rate_stress = pd.DataFrame(rate_stress_rows)

    liq = liquidity_gap_table(liquidity)
    cum_7d = float(liq[liq["bucket_order"] <= 2]["net_gap_bn_vnd"].sum())
    cum_30d = float(liq[liq["bucket_order"] <= 3]["net_gap_bn_vnd"].sum())

    liq_stress_rows = []
    for row in scenarios.to_dict("records"):
        liq_stress_rows.append({
            **row,
            "stressed_gap_7d_bn_vnd": liquidity_stress_gap_bn(liquidity, through_bucket_order=2, outflow_addon_pct=float(row["liquidity_outflow_addon_pct"])),
            "stressed_gap_30d_bn_vnd": liquidity_stress_gap_bn(liquidity, through_bucket_order=3, outflow_addon_pct=float(row["liquidity_outflow_addon_pct"])),
        })
    liq_stress = pd.DataFrame(liq_stress_rows)

    severe = scenarios[scenarios["scenario_id"].astype(str).eq("SEVERE")]
    severe_id = "SEVERE" if not severe.empty else str(scenarios.iloc[-1]["scenario_id"])
    severe_fx = fx_stress[fx_stress["scenario_id"].astype(str).eq(severe_id)]
    severe_rate = rate_stress[rate_stress["scenario_id"].astype(str).eq(severe_id)]
    fx_loss = float(severe_fx.iloc[0]["fx_loss_bn_vnd"]) if not severe_fx.empty and pd.notna(severe_fx.iloc[0]["fx_loss_bn_vnd"]) else None
    rate_loss = float(severe_rate.iloc[0]["rates_loss_bn_vnd"]) if not severe_rate.empty else None

    limit_rows = [
        _limit_record(limits, "FX_USD_NOP_MN", usd_nop),
        _limit_record(limits, "FX_STRESS_LOSS_BN", fx_loss),
        _limit_record(limits, "RATES_PV01_BN_PER_BP", total_pv01),
        _limit_record(limits, "RATES_STRESS_LOSS_BN", rate_loss),
        _limit_record(limits, "LIQ_CUM_GAP_7D_BN", cum_7d),
        _limit_record(limits, "LIQ_CUM_GAP_30D_BN", cum_30d),
    ]

    return {
        "market": market,
        "fx_positions": fx_positions,
        "usd_nop_mn": usd_nop,
        "fx_stress": fx_stress,
        "bond_positions": bonds,
        "total_pv01_bn_per_bp": total_pv01,
        "rate_stress": rate_stress,
        "liquidity_gap": liq,
        "cumulative_gap_7d_bn_vnd": cum_7d,
        "cumulative_gap_30d_bn_vnd": cum_30d,
        "liquidity_stress": liq_stress,
        "limits": pd.DataFrame(limit_rows),
        "readiness": history_readiness(store),
    }
