"""Deterministic banking market & liquidity risk core.

Public market data provides risk factors. Bank positions/limits in the portfolio
are synthetic and are explicitly labelled as such.
"""

from .engine import build_risk_snapshot

__all__ = ["build_risk_snapshot"]
