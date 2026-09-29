from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from src.risk_core.engine import build_risk_snapshot
from src.risk_core.market_inputs import assess_yield_change
from src.risk_core.metrics import (
    bond_pnl_from_yield_move_bn,
    bond_pv01_bn,
    fx_stress_pnl_bn_vnd,
    limit_status,
    limit_utilization,
    liquidity_gap_table,
)


def test_pv01_and_rate_pnl():
    pv01 = bond_pv01_bn(1500, 7.2)
    assert math.isclose(pv01, 1.08, rel_tol=1e-9)
    assert math.isclose(bond_pnl_from_yield_move_bn(pv01, 10), -10.8, rel_tol=1e-9)


def test_fx_stress_short_usd_loses_when_usd_rises():
    pnl = fx_stress_pnl_bn_vnd(-32, 26000, 3.0)
    assert pnl is not None
    assert math.isclose(pnl, -24.96, rel_tol=1e-9)


def test_limit_bands():
    assert limit_status(limit_utilization(39, 50)) == "NORMAL"
    assert limit_status(limit_utilization(40, 50)) == "WATCH"
    assert limit_status(limit_utilization(45, 50)) == "WARNING"
    assert limit_status(limit_utilization(51, 50)) == "BREACH"


def test_liquidity_gap_is_cumulative():
    df = pd.DataFrame([
        {"bucket": "1D", "bucket_order": 1, "inflows_bn_vnd": 100, "outflows_bn_vnd": 150},
        {"bucket": "2-7D", "bucket_order": 2, "inflows_bn_vnd": 80, "outflows_bn_vnd": 40},
    ])
    out = liquidity_gap_table(df)
    assert out.iloc[0]["net_gap_bn_vnd"] == -50
    assert out.iloc[1]["cumulative_gap_bn_vnd"] == -10


class FakeStore:
    def __init__(self):
        self.rows = [
            {"metric_id": "VIRA.FX.INTERBANK", "entity_id": "INTERBANK", "value": 26000.0, "period_end": "2026-09-28", "fetched_at": "2026-09-29T01:00:00+00:00", "source": "VIRA", "quality_flag": "C"},
            {"metric_id": "HNX.GOV.TENOR_YIELD", "entity_id": "GOV_TENOR:5Y", "value": 4.30, "period_end": "2026-09-28", "fetched_at": "2026-09-29T01:00:00+00:00", "source": "HNX", "quality_flag": "B"},
            {"metric_id": "HNX.GOV.TENOR_YIELD", "entity_id": "GOV_TENOR:10Y", "value": 4.46, "period_end": "2026-09-28", "fetched_at": "2026-09-29T01:00:00+00:00", "source": "HNX", "quality_flag": "B"},
            {"metric_id": "HNX.GOV.TENOR_YIELD", "entity_id": "GOV_TENOR:15Y", "value": 4.58, "period_end": "2026-09-28", "fetched_at": "2026-09-29T01:00:00+00:00", "source": "HNX", "quality_flag": "B"},
        ]

    def latest_observations(self, limit=5000):
        return self.rows[:limit]

    def latest_observation(self, metric_id, entity_id, before_period=None):
        return None

    def recent_observations(self, source=None, limit=10000):
        rows = self.rows
        if source is not None:
            rows = [r for r in rows if r.get("source") == source]
        return rows[:limit]


def test_snapshot_uses_public_market_factor_and_synthetic_book():
    snap = build_risk_snapshot(FakeStore(), book_dir=Path("config/risk_book"))
    assert snap["usd_nop_mn"] == -32.0
    expected = 800 * 4.3 * 0.0001 + 900 * 7.2 * 0.0001 + 350 * 9.8 * 0.0001
    assert math.isclose(snap["total_pv01_bn_per_bp"], expected, rel_tol=1e-9)
    severe = snap["fx_stress"].query("scenario_id == 'SEVERE'").iloc[0]
    assert severe["fx_loss_bn_vnd"] > 0



def test_yield_change_dq_accepts_comparable_move():
    current = {
        "metric_id": "HNX.GOV.TENOR_YIELD",
        "entity_id": "GOV_TENOR:10Y",
        "source": "HNX",
        "period_end": "2026-09-29",
        "value": 4.40,
    }
    previous = {
        "metric_id": "HNX.GOV.TENOR_YIELD",
        "entity_id": "GOV_TENOR:10Y",
        "source": "HNX",
        "period_end": "2026-09-28",
        "value": 4.46,
    }

    out = assess_yield_change(current, previous)

    assert out["dq_status"] == "VALID"
    assert math.isclose(out["validated_change_bp"], -6.0, abs_tol=1e-9)


def test_yield_change_dq_blocks_extreme_move_from_pnl():
    current = {
        "metric_id": "HNX.GOV.TENOR_YIELD",
        "entity_id": "GOV_TENOR:15Y",
        "source": "HNX",
        "period_end": "2026-09-29",
        "value": 4.632366,
    }
    previous = {
        "metric_id": "HNX.GOV.TENOR_YIELD",
        "entity_id": "GOV_TENOR:15Y",
        "source": "HNX",
        "period_end": "2026-09-28",
        "value": 2.971156,
    }

    out = assess_yield_change(current, previous)

    assert out["dq_status"] == "OUTLIER_REVIEW"
    assert out["raw_change_bp"] > 100
    assert out["validated_change_bp"] is None
