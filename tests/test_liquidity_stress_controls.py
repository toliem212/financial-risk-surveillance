from __future__ import annotations

import pandas as pd

from src.risk_core.liquidity_stress_controls import (
    liquidity_stress_limit_table,
    stress_control_summary,
    stress_limit_insights,
)


def _snapshot():
    return {
        "liquidity_stress": pd.DataFrame([
            {
                "scenario_id": "MODERATE",
                "scenario_name": "Moderate market and funding shock",
                "liquidity_outflow_addon_pct": 5.0,
                "stressed_gap_7d_bn_vnd": -1280.0,
                "stressed_gap_30d_bn_vnd": -1040.0,
            },
            {
                "scenario_id": "SEVERE",
                "scenario_name": "Severe combined market and funding shock",
                "liquidity_outflow_addon_pct": 10.0,
                "stressed_gap_7d_bn_vnd": -1660.0,
                "stressed_gap_30d_bn_vnd": -1780.0,
            },
            {
                "scenario_id": "EXTREME",
                "scenario_name": "Extreme combined market and funding shock",
                "liquidity_outflow_addon_pct": 20.0,
                "stressed_gap_7d_bn_vnd": -2420.0,
                "stressed_gap_30d_bn_vnd": -3260.0,
            },
        ]),
        "limits": pd.DataFrame([
            {
                "metric_id": "LIQ_CUM_GAP_7D_BN",
                "limit_value": 1500.0,
                "utilization_pct": 60.0,
                "status": "NORMAL",
            },
            {
                "metric_id": "LIQ_CUM_GAP_30D_BN",
                "limit_value": 2500.0,
                "utilization_pct": 12.0,
                "status": "NORMAL",
            },
        ]),
    }


def test_stress_table_uses_business_friendly_labels():
    out = liquidity_stress_limit_table(_snapshot())
    assert out.iloc[0]["scenario_label"] == "Căng thẳng vừa"
    assert out.iloc[1]["scenario_label"] == "Căng thẳng mạnh"
    assert out.iloc[2]["scenario_label"] == "Căng thẳng cực đoan"


def test_stress_summary_finds_first_watch_and_breach():
    out = stress_control_summary(_snapshot())
    assert out["first_watch_addon_pct"] == 5.0
    assert out["first_breach_addon_pct"] == 10.0
    assert out["first_breach_horizons"] == ["7D"]


def test_stress_insights_are_condensed():
    text = " ".join(stress_limit_insights(_snapshot()))
    assert "stress +5%" in text
    assert "85.3%" in text
    assert "stress +10%" in text
    assert "110.7%" in text
    assert "161.3%" in text
    assert "130.4%" in text
