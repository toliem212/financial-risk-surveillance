from __future__ import annotations

import math

import pandas as pd

from src.risk_core.var_es import (
    expected_shortfall_from_pnl,
    fx_position_pnl_bn,
    historical_var_from_pnl,
    parametric_var_from_pnl,
    rate_portfolio_pnl_bn,
    rolling_historical_var_backtest,
    simple_returns,
    yield_changes_bp,
    _scope_report,
)


def test_simple_returns():
    out = simple_returns(pd.Series([100.0, 101.0, 99.99]))
    assert len(out) == 2
    assert math.isclose(out.iloc[0], 0.01, rel_tol=1e-12)
    assert math.isclose(out.iloc[1], -0.01, rel_tol=1e-12)


def test_yield_changes_bp():
    out = yield_changes_bp(pd.Series([4.00, 4.05, 4.02]))
    assert list(out.round(8)) == [5.0, -3.0]


def test_historical_var_and_es_are_losses():
    pnl = pd.Series([-10.0, -5.0, 0.0, 2.0, 4.0])
    var = historical_var_from_pnl(pnl, confidence=0.80)
    es = expected_shortfall_from_pnl(pnl, confidence=0.80)
    assert var is not None and var > 0
    assert es is not None and es >= var


def test_parametric_var_positive_for_volatile_pnl():
    pnl = pd.Series([-4.0, -2.0, 0.0, 1.0, 5.0])
    var = parametric_var_from_pnl(pnl, confidence=0.99)
    assert var is not None and var > 0


def test_rate_portfolio_pnl_sign_convention():
    changes = pd.DataFrame({"5Y": [10.0], "10Y": [-5.0]})
    pnl = rate_portfolio_pnl_bn(changes, {"5Y": 0.4, "10Y": 0.8})
    # -0.4*10 - 0.8*(-5) = 0
    assert math.isclose(float(pnl.iloc[0]), 0.0, abs_tol=1e-12)


def test_fx_position_pnl_short_usd_loses_when_usd_rises():
    pnl = fx_position_pnl_bn(pd.Series([0.03]), -32.0, 25980.0)
    assert math.isclose(float(pnl.iloc[0]), -24.9408, rel_tol=1e-12)


def test_rolling_backtest_detects_tail_exception():
    # Stable history followed by one much larger loss.
    pnl = pd.Series([0.0] * 250 + [-100.0])
    out = rolling_historical_var_backtest(pnl, confidence=0.99, window=250)
    assert out["observations"] == 1
    assert out["exceptions"] == 1
    assert math.isclose(out["exception_rate_pct"], 100.0)


def test_scope_report_is_indicative_for_230_observations():
    pnl = pd.Series([float((i % 11) - 5) for i in range(230)])
    out = _scope_report("Rates / TPCP", pnl, sessions=249, dq_excluded=6)
    assert out["status"] == "INDICATIVE"
    assert out["pnl_observations"] == 230
    assert out["minimum_required"] == 250
    assert out["historical_var_99_bn"] is not None
    assert out["backtest_observations"] == 0


def test_scope_report_is_ready_at_250_observations():
    pnl = pd.Series([float((i % 13) - 6) for i in range(250)])
    out = _scope_report("Rates / TPCP", pnl, sessions=269, dq_excluded=0)
    assert out["status"] == "READY"
    assert out["pnl_observations"] == 250


def test_scope_report_not_ready_below_indicative_gate():
    pnl = pd.Series([float((i % 7) - 3) for i in range(199)])
    out = _scope_report("Rates / TPCP", pnl, sessions=210, dq_excluded=0)
    assert out["status"] == "NOT_READY"
    assert out["historical_var_99_bn"] is None
