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
from src.storage.factory import create_store
from src.ui.display import render_sidebar

st.set_page_config(page_title="Liquidity Risk", layout="wide")
render_sidebar()
st.title("Liquidity Risk")
st.caption(
    "Lãi suất liên ngân hàng và OMO là market-liquidity context từ nguồn công khai. "
    "Cash-flow gap là synthetic banking-book data; không phải LCR/NSFR của một ngân hàng thực."
)

store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
try:
    snap = build_risk_snapshot(store)
finally:
    store.close()

market = snap["market"]
on_rate = market["ibor_vnd_on"].get("rate_pct")

c1, c2, c3, c4 = st.columns(4)
c1.metric("VND O/N (%)", "N/A" if on_rate is None else f"{on_rate:,.2f}")
c2.metric("OMO net (tỷ VND)", "N/A" if market.get("omo_net") is None else f"{market['omo_net']:,.0f}")
c3.metric("Cumulative GAP 7D (tỷ VND)", f"{snap['cumulative_gap_7d_bn_vnd']:,.0f}")
c4.metric("Cumulative GAP 30D (tỷ VND)", f"{snap['cumulative_gap_30d_bn_vnd']:,.0f}")

st.subheader("Contractual liquidity-gap ladder — synthetic")
liq = snap["liquidity_gap"][[
    "bucket", "inflows_bn_vnd", "outflows_bn_vnd", "net_gap_bn_vnd", "cumulative_gap_bn_vnd"
]].copy()
st.dataframe(liq, width="stretch", hide_index=True)

st.subheader("Funding outflow stress")
st.dataframe(
    snap["liquidity_stress"][[
        "scenario_id", "scenario_name", "liquidity_outflow_addon_pct",
        "stressed_gap_7d_bn_vnd", "stressed_gap_30d_bn_vnd"
    ]],
    width="stretch",
    hide_index=True,
)

st.subheader("Liquidity limits")
limits = snap["limits"]
liq_limits = limits[limits["metric_id"].astype(str).isin(["LIQ_CUM_GAP_7D_BN", "LIQ_CUM_GAP_30D_BN"])]
st.dataframe(liq_limits, width="stretch", hide_index=True)

st.info(
    "Phạm vi MVP hiện tại là liquidity-gap monitoring và stress. LCR/NSFR chỉ nên được tính khi có cấu phần HQLA, "
    "cash inflow/outflow 30D, ASF và RSF ở cấp bảng cân đối; dữ liệu công khai hiện tại không đủ để gọi một con số LCR/NSFR là số thực của ngân hàng."
)
