from __future__ import annotations

import pandas as pd

from src.risk_core.control_room import (
    action_queue,
    control_room_summary,
    stress_control_table,
)


def _snapshot():
    return {
        "limits": pd.DataFrame([
            {"metric_id": "FX_USD_NOP_MN", "current_value": 32.0, "limit_value": 50.0, "unit": "USD_mn", "utilization_pct": 64.0, "status": "NORMAL"},
            {"metric_id": "FX_STRESS_LOSS_BN", "current_value": 24.9408, "limit_value": 30.0, "unit": "VND_bn", "utilization_pct": 83.136, "status": "WATCH"},
            {"metric_id": "RATES_PV01_BN_PER_BP", "current_value": 1.335, "limit_value": 1.5, "unit": "VND_bn_per_bp", "utilization_pct": 89.0, "status": "WATCH"},
            {"metric_id": "RATES_STRESS_LOSS_BN", "current_value": 133.5, "limit_value": 150.0, "unit": "VND_bn", "utilization_pct": 89.0, "status": "WATCH"},
            {"metric_id": "LIQ_CUM_GAP_7D_BN", "current_value": -900.0, "limit_value": 1500.0, "unit": "VND_bn", "utilization_pct": 60.0, "status": "NORMAL"},
            {"metric_id": "LIQ_CUM_GAP_30D_BN", "current_value": -300.0, "limit_value": 2500.0, "unit": "VND_bn", "utilization_pct": 12.0, "status": "NORMAL"},
        ]),
        "fx_stress": pd.DataFrame([
            {"scenario_id": "MODERATE", "fx_usd_vnd_shock_pct": 1.5, "fx_loss_bn_vnd": 12.4704},
            {"scenario_id": "SEVERE", "fx_usd_vnd_shock_pct": 3.0, "fx_loss_bn_vnd": 24.9408},
            {"scenario_id": "EXTREME", "fx_usd_vnd_shock_pct": 5.0, "fx_loss_bn_vnd": 41.568},
        ]),
        "rate_stress": pd.DataFrame([
            {"scenario_id": "MODERATE", "rates_parallel_bp": 50.0, "rates_loss_bn_vnd": 66.75},
            {"scenario_id": "SEVERE", "rates_parallel_bp": 100.0, "rates_loss_bn_vnd": 133.5},
            {"scenario_id": "EXTREME", "rates_parallel_bp": 200.0, "rates_loss_bn_vnd": 267.0},
        ]),
        "liquidity_stress": pd.DataFrame([
            {"scenario_id": "MODERATE", "liquidity_outflow_addon_pct": 5.0, "stressed_gap_7d_bn_vnd": -1280.0, "stressed_gap_30d_bn_vnd": -1040.0},
            {"scenario_id": "SEVERE", "liquidity_outflow_addon_pct": 10.0, "stressed_gap_7d_bn_vnd": -1660.0, "stressed_gap_30d_bn_vnd": -1780.0},
            {"scenario_id": "EXTREME", "liquidity_outflow_addon_pct": 20.0, "stressed_gap_7d_bn_vnd": -2420.0, "stressed_gap_30d_bn_vnd": -3260.0},
        ]),
    }


def test_compact_stress_summary_is_readable():
    out = stress_control_table(_snapshot())
    moderate = out.iloc[0]
    severe = out.iloc[1]
    extreme = out.iloc[2]

    assert moderate["conclusion"] == "Theo dõi: Thanh khoản 7D"
    assert severe["conclusion"] == "Vượt: Thanh khoản 7D"
    assert "FX" in extreme["conclusion"]
    assert "Lãi suất" in extreme["conclusion"]
    assert extreme["breach_count"] == 4


def test_summary_keeps_expected_control_room_counts():
    out = control_room_summary(_snapshot())
    assert out["base_breach_count"] == 0
    assert out["base_attention_count"] == 3
    assert out["first_stress_breach_scenario"] == "Căng thẳng mạnh"
    assert out["max_stress_breach_count"] == 4


def test_action_queue_translates_stress_control_name():
    out = action_queue(_snapshot())
    urgent = out.iloc[0]
    assert urgent["priority"] == "KHẨN"
    assert "Thanh khoản 7D" in urgent["trigger"]
    assert "Liquidity 7D" not in urgent["trigger"]
