from __future__ import annotations

import pandas as pd

from src.risk_core.liquidity_insights import (
    build_liquidity_insights,
    liquidity_limit_summary,
    worst_liquidity_stress,
)


def _snapshot():
    return {
        "cumulative_gap_7d_bn_vnd": -900.0,
        "cumulative_gap_30d_bn_vnd": -300.0,
        "market": {
            "ibor_vnd_on": {"rate_pct": 0.5},
            "omo_net": 9814.0,
        },
        "liquidity_stress": pd.DataFrame([
            {
                "scenario_id": "MODERATE",
                "scenario_name": "Moderate",
                "liquidity_outflow_addon_pct": 10.0,
                "stressed_gap_7d_bn_vnd": -1660.0,
                "stressed_gap_30d_bn_vnd": -1780.0,
            },
            {
                "scenario_id": "SEVERE",
                "scenario_name": "Severe",
                "liquidity_outflow_addon_pct": 20.0,
                "stressed_gap_7d_bn_vnd": -2420.0,
                "stressed_gap_30d_bn_vnd": -3260.0,
            },
        ]),
        "limits": pd.DataFrame([
            {
                "metric_id": "LIQ_CUM_GAP_7D_BN",
                "utilization_pct": 60.0,
                "status": "NORMAL",
            },
            {
                "metric_id": "LIQ_CUM_GAP_30D_BN",
                "utilization_pct": 12.0,
                "status": "NORMAL",
            },
        ]),
    }


def test_worst_liquidity_stress_uses_largest_outflow_addon():
    out = worst_liquidity_stress(_snapshot())
    assert out["scenario_id"] == "SEVERE"
    assert out["addon_pct"] == 20.0
    assert out["gap_30d_bn"] == -3260.0


def test_liquidity_limit_summary_uses_highest_utilization():
    out = liquidity_limit_summary(_snapshot())
    assert out["max_utilization_pct"] == 60.0
    assert out["status"] == "NORMAL"
    assert out["status_vi"] == "BÌNH THƯỜNG"


def test_liquidity_insights_explain_gap_recovery_and_stress():
    insights = build_liquidity_insights(_snapshot())
    text = " ".join(insights)
    assert "900 tỷ VND" in text
    assert "cải thiện 600 tỷ VND" in text
    assert "3,260 tỷ VND" in text
    assert "60.0%" in text


def test_liquidity_insights_include_market_context():
    text = " ".join(build_liquidity_insights(_snapshot()))
    assert "O/N VND 0.50%" in text
    assert "OMO bơm ròng 9,814 tỷ VND" in text
