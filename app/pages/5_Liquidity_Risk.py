from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from src.risk_core.engine import build_risk_snapshot
from src.risk_core.liquidity_insights import (
    STATUS_VI,
    build_liquidity_insights,
    liquidity_limit_summary,
    worst_liquidity_stress,
)
from src.risk_core.liquidity_stress_controls import (
    liquidity_stress_limit_table,
    stress_control_summary,
    stress_limit_insights,
)
from src.storage.factory import create_store
from src.ui.display import render_sidebar

st.set_page_config(page_title="Liquidity Risk", layout="wide")
render_sidebar()

st.title("Liquidity Risk — Thanh khoản ngắn hạn")
st.caption(
    "Theo dõi chênh lệch dòng tiền theo kỳ hạn, sức chịu đựng dưới stress và mức sử dụng hạn mức. "
    "Dòng tiền/hạn mức là danh mục ngân hàng mô phỏng; O/N và OMO là dữ liệu thị trường công khai."
)

store = create_store(
    local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db"))
)
try:
    snap = build_risk_snapshot(store)
finally:
    store.close()

market = snap["market"]
on_rate = market["ibor_vnd_on"].get("rate_pct")
omo_net = market.get("omo_net")
liq = snap["liquidity_gap"][[
    "bucket",
    "inflows_bn_vnd",
    "outflows_bn_vnd",
    "net_gap_bn_vnd",
    "cumulative_gap_bn_vnd",
]].copy()

gap_1d = float(liq.iloc[0]["cumulative_gap_bn_vnd"]) if not liq.empty else None
gap_7d = float(snap["cumulative_gap_7d_bn_vnd"])
gap_30d = float(snap["cumulative_gap_30d_bn_vnd"])
worst = worst_liquidity_stress(snap)
limit_summary = liquidity_limit_summary(snap)
stress_limits = liquidity_stress_limit_table(snap)
stress_summary = stress_control_summary(snap)

c1, c2, c3, c4 = st.columns(4)
c1.metric("GAP lũy kế 1 ngày", "N/A" if gap_1d is None else f"{gap_1d:,.0f} tỷ")
c2.metric("GAP lũy kế 7 ngày", f"{gap_7d:,.0f} tỷ")
c3.metric("GAP lũy kế 30 ngày", f"{gap_30d:,.0f} tỷ")
c4.metric(
    "GAP 30 ngày dưới stress",
    "N/A" if worst["gap_30d_bn"] is None else f"{worst['gap_30d_bn']:,.0f} tỷ",
)

util = limit_summary["max_utilization_pct"]
if util is not None:
    st.markdown(
        f"**Mức sử dụng hạn mức cao nhất ở trạng thái cơ sở: "
        f"{util:,.1f}% · {limit_summary['status_vi']}**"
    )

breach_addon = stress_summary["first_breach_addon_pct"]
if breach_addon is not None:
    st.error(
        f"Khả năng chịu stress: hạn mức bắt đầu bị vượt từ kịch bản "
        f"+{breach_addon:,.0f}% dòng tiền ra."
    )

st.markdown("### Nhận định chính")
base_insights = build_liquidity_insights(snap)

# Keep the page focused: use the first two balance-sheet observations,
# the market context, then the stress-control conclusions.
selected_base = []
for line in base_insights:
    if (
        line.startswith("Trong 7 ngày")
        or line.startswith("Đến 30 ngày")
        or line.startswith("Bối cảnh thị trường tiền tệ")
    ):
        selected_base.append(line)

for insight in selected_base + stress_limit_insights(snap):
    st.markdown(f"- {insight}")

st.markdown("### Dòng tiền theo kỳ hạn")
liq_display = liq.rename(
    columns={
        "bucket": "Kỳ hạn",
        "inflows_bn_vnd": "Dòng tiền vào",
        "outflows_bn_vnd": "Dòng tiền ra",
        "net_gap_bn_vnd": "GAP kỳ",
        "cumulative_gap_bn_vnd": "GAP lũy kế",
    }
)
st.dataframe(liq_display, width="stretch", hide_index=True)
st.caption(
    "Đơn vị: tỷ VND. GAP âm cho thấy dòng tiền ra lớn hơn dòng tiền vào "
    "trong phạm vi kỳ hạn tương ứng."
)

st.markdown("### Stress thanh khoản")
if stress_limits.empty:
    st.info("Chưa có dữ liệu stress thanh khoản.")
else:
    stress_display = stress_limits.copy()
    stress_display["Kết luận"] = (
        "7D: "
        + stress_display["status_7d_vi"].astype(str)
        + " · 30D: "
        + stress_display["status_30d_vi"].astype(str)
    )
    stress_display = stress_display.rename(
        columns={
            "scenario_label": "Kịch bản",
            "liquidity_outflow_addon_pct": "Tăng dòng tiền ra (%)",
            "stressed_gap_7d_bn_vnd": "GAP 7D",
            "utilization_7d_pct": "Sử dụng HM 7D (%)",
            "stressed_gap_30d_bn_vnd": "GAP 30D",
            "utilization_30d_pct": "Sử dụng HM 30D (%)",
        }
    )[[
        "Kịch bản",
        "Tăng dòng tiền ra (%)",
        "GAP 7D",
        "Sử dụng HM 7D (%)",
        "GAP 30D",
        "Sử dụng HM 30D (%)",
        "Kết luận",
    ]]
    st.dataframe(stress_display, width="stretch", hide_index=True)

    if breach_addon is not None:
        st.error(
            f"Từ stress +{breach_addon:,.0f}% dòng tiền ra, ít nhất một hạn mức thanh khoản "
            "bị vượt. Đây là điểm kích hoạt rà soát funding contingency và escalation."
        )

if worst["gap_30d_bn"] is not None:
    deterioration_30d = worst["gap_30d_bn"] - gap_30d
    st.caption(
        f"Kịch bản cao nhất: GAP 30 ngày từ {gap_30d:,.0f} xuống "
        f"{worst['gap_30d_bn']:,.0f} tỷ VND, xấu đi "
        f"{abs(deterioration_30d):,.0f} tỷ VND."
    )

st.markdown("### Bối cảnh thị trường tiền tệ")
m1, m2 = st.columns(2)
m1.metric(
    "Lãi suất VND O/N",
    "N/A" if on_rate is None else f"{float(on_rate):,.2f}%",
)
if omo_net is None:
    m2.metric("OMO ròng", "N/A")
else:
    omo_direction = (
        "Bơm ròng" if float(omo_net) > 0
        else "Hút ròng" if float(omo_net) < 0
        else "Cân bằng"
    )
    m2.metric("OMO ròng", f"{omo_direction} {abs(float(omo_net)):,.0f} tỷ")

st.caption(
    "O/N phản ánh giá vốn ngắn hạn trên thị trường liên ngân hàng; OMO phản ánh trạng thái "
    "bơm/hút ròng qua nghiệp vụ thị trường mở. Hai chỉ báo được dùng làm bối cảnh, "
    "không thay thế cho dòng tiền nội bảng."
)

st.markdown("### Hạn mức & cảnh báo sớm")
limits = snap["limits"]
liq_limits = limits[
    limits["metric_id"].astype(str).isin(
        ["LIQ_CUM_GAP_7D_BN", "LIQ_CUM_GAP_30D_BN"]
    )
].copy()

metric_vi = {
    "LIQ_CUM_GAP_7D_BN": "GAP lũy kế 7 ngày",
    "LIQ_CUM_GAP_30D_BN": "GAP lũy kế 30 ngày",
}
liq_limits["Chỉ tiêu"] = liq_limits["metric_id"].astype(str).map(metric_vi)
liq_limits["Trạng thái"] = (
    liq_limits["status"].astype(str).map(STATUS_VI).fillna(liq_limits["status"])
)
limit_display = liq_limits.rename(
    columns={
        "current_value": "Giá trị hiện tại",
        "limit_value": "Hạn mức",
        "utilization_pct": "Sử dụng hạn mức (%)",
    }
)[[
    "Chỉ tiêu",
    "Giá trị hiện tại",
    "Hạn mức",
    "Sử dụng hạn mức (%)",
    "Trạng thái",
]]
st.dataframe(limit_display, width="stretch", hide_index=True)

with st.expander("Phạm vi dữ liệu & phương pháp"):
    st.markdown(
        """
- **Dòng tiền và hạn mức:** dữ liệu mô phỏng để thể hiện quy trình giám sát của ngân hàng.
- **O/N và OMO:** dữ liệu thị trường công khai, dùng làm bối cảnh thanh khoản hệ thống.
- **Stress:** tăng giả định dòng tiền ra theo từng kịch bản và tính lại GAP lũy kế 7D/30D.
- **Hạn mức dưới stress:** sử dụng cùng hạn mức mô phỏng của trạng thái cơ sở để đánh giá sức chịu đựng.
- **LCR/NSFR:** được bổ sung khi mô hình có đầy đủ HQLA, dòng tiền 30 ngày, ASF và RSF ở cấp bảng cân đối.
        """
    )
