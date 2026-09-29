from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from src.risk_core.engine import build_risk_snapshot
from src.risk_core.metrics import limit_status, limit_utilization
from src.storage.factory import create_store
from src.ui.display import render_sidebar

st.set_page_config(page_title="Limits & Stress", layout="wide")
render_sidebar()
st.title("Limits & Early Warning / Stress Testing")
st.caption("Rule-based control layer: NORMAL < 80% · WATCH 80–<90% · WARNING 90–100% · BREACH > 100%.")

store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
try:
    snap = build_risk_snapshot(store)
finally:
    store.close()

limits = snap["limits"].copy()

status_order = {"BREACH": 0, "WARNING": 1, "WATCH": 2, "NORMAL": 3, "NOT_AVAILABLE": 4}
limits["_order"] = limits["status"].map(status_order).fillna(9)
limits = limits.sort_values(["_order", "utilization_pct"], ascending=[True, False]).drop(columns=["_order"])

counts = limits["status"].value_counts().to_dict()
c1, c2, c3, c4 = st.columns(4)
c1.metric("BREACH", int(counts.get("BREACH", 0)))
c2.metric("WARNING", int(counts.get("WARNING", 0)))
c3.metric("WATCH", int(counts.get("WATCH", 0)))
c4.metric("NORMAL", int(counts.get("NORMAL", 0)))

st.subheader("Limit utilization")
st.dataframe(limits, width="stretch", hide_index=True)

st.subheader("Combined scenario view")
fx = snap["fx_stress"][["scenario_id", "scenario_name", "fx_loss_bn_vnd"]].copy()
rates = snap["rate_stress"][["scenario_id", "rates_loss_bn_vnd"]].copy()
liq = snap["liquidity_stress"][["scenario_id", "stressed_gap_7d_bn_vnd", "stressed_gap_30d_bn_vnd"]].copy()
combined = fx.merge(rates, on="scenario_id", how="outer").merge(liq, on="scenario_id", how="outer")
combined["market_loss_bn_vnd"] = combined[["fx_loss_bn_vnd", "rates_loss_bn_vnd"]].sum(axis=1, min_count=1)
st.dataframe(combined, width="stretch", hide_index=True)
st.caption(
    "Market loss (FX + rates) có cùng đơn vị P&L nên có thể cộng trong mô phỏng. Liquidity gap là thiếu hụt dòng tiền, "
    "được giữ riêng và không cộng cơ học vào P&L."
)

severe_liq = combined[combined["scenario_id"].astype(str).eq("SEVERE")]
if not severe_liq.empty:
    gap7 = float(severe_liq.iloc[0]["stressed_gap_7d_bn_vnd"])
    limit7_row = limits[limits["metric_id"].astype(str).eq("LIQ_CUM_GAP_7D_BN")]
    if not limit7_row.empty:
        limit7 = float(limit7_row.iloc[0]["limit_value"])
        util = limit_utilization(gap7, limit7)
        status = limit_status(util)
        st.warning(f"Severe 7D stressed liquidity gap: {gap7:,.0f} tỷ VND · utilization {util:,.1f}% · {status}")

st.subheader("Control interpretation")
st.markdown(
    """
- **NORMAL:** theo dõi định kỳ.
- **WATCH:** tăng tần suất giám sát và kiểm tra driver.
- **WARNING:** điều tra exposure/hedge/funding plan và chuẩn bị escalation.
- **BREACH:** mở exception, xác nhận dữ liệu, xác định nguyên nhân và escalation theo quy trình.

Các trạng thái này là framework mô phỏng cho portfolio; không phải hạn mức nội bộ của một tổ chức cụ thể.
"""
)
