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

st.set_page_config(page_title="Market Risk", layout="wide")
render_sidebar()
st.title("Market Risk")
st.caption(
    "Risk factors lấy từ dữ liệu thị trường công khai; vị thế và hạn mức ngân hàng trong trang này là synthetic, "
    "được thiết kế để mô phỏng quy trình kiểm soát rủi ro chứ không đại diện cho bất kỳ ngân hàng cụ thể nào."
)

store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
try:
    snap = build_risk_snapshot(store)
finally:
    store.close()

market = snap["market"]
fx = market["fx_usd_vnd"]
limits = snap["limits"]

usd_nop = snap["usd_nop_mn"]
spot = fx.get("spot")
severe_fx = snap["fx_stress"].query("scenario_id == 'SEVERE'")
severe_fx_loss = None if severe_fx.empty else severe_fx.iloc[0]["fx_loss_bn_vnd"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("USD NOP (triệu USD)", f"{usd_nop:,.1f}")
c2.metric("USD/VND liên ngân hàng", "N/A" if spot is None else f"{spot:,.0f}")
c3.metric("Tổng PV01 TPCP (tỷ VND/bp)", f"{snap['total_pv01_bn_per_bp']:,.3f}")
c4.metric("FX stress loss — Severe (tỷ VND)", "N/A" if pd.isna(severe_fx_loss) else f"{float(severe_fx_loss):,.1f}")

if spot is None:
    st.warning(
        "C\u00f3 quan s\u00e1t d\u1eef li\u1ec7u th\u1ecb tr\u01b0\u1eddng ch\u01b0a qua Data Quality Gate. "
        "Bi\u1ebfn \u0111\u1ed9ng th\u1ecb tr\u01b0\u1eddng g\u1ed1c v\u1eabn \u0111\u01b0\u1ee3c hi\u1ec3n th\u1ecb \u0111\u1ec3 \u0111i\u1ec1u tra, "
        "nh\u01b0ng kh\u00f4ng \u0111\u01b0\u1ee3c t\u1ef1 \u0111\u1ed9ng s\u1eed d\u1ee5ng cho estimated market P&L."
    )
    st.dataframe(
        dq_review[
            [
                "bond_bucket",
                "market_yield_pct",
                "previous_yield_pct",
                "previous_period_end",
                "raw_yield_change_bp",
                "market_dq_status",
                "market_dq_reason",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
st.caption(
    "PV01 ở đây là sensitivity-based approximation: Market Value × Modified Duration × 1bp. "
    "Không được trình bày như định giá cash-flow chính xác của một mã trái phiếu cụ thể."
)

st.subheader("Parallel-rate stress")
st.dataframe(
    snap["rate_stress"][["scenario_id", "scenario_name", "rates_parallel_bp", "rates_pnl_bn_vnd", "rates_loss_bn_vnd"]],
    width="stretch",
    hide_index=True,
)

st.subheader("Market-risk limits")
market_limits = limits[limits["metric_id"].astype(str).isin([
    "FX_USD_NOP_MN", "FX_STRESS_LOSS_BN", "RATES_PV01_BN_PER_BP", "RATES_STRESS_LOSS_BN"
])]
st.dataframe(market_limits, width="stretch", hide_index=True)

st.subheader("Độ sẵn sàng dữ liệu lịch sử cho VaR / ES")
st.dataframe(snap["readiness"], width="stretch", hide_index=True)
st.caption(
    "Historical VaR/ES chỉ được bật khi chuỗi lịch sử đạt ngưỡng tối thiểu đã công bố. "
    "Cho đến khi đủ mẫu, dashboard giữ trạng thái chưa sẵn sàng thay vì suy diễn độ chính xác giả."
)
