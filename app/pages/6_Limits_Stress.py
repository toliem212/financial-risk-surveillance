from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from src.risk_core.control_room import (
    METRIC_VI,
    STATUS_VI,
    action_queue,
    base_limit_control_table,
    control_room_summary,
    management_insights,
    stress_control_table,
)
from src.risk_core.engine import build_risk_snapshot
from src.storage.factory import create_store
from src.ui.display import render_sidebar

st.set_page_config(page_title="Limits & EWS / Stress Testing", layout="wide")
render_sidebar()

st.title("Limits & EWS — Control Room")
st.caption(
    "Tổng hợp trạng thái hạn mức, cảnh báo sớm và sức chịu đựng dưới stress để xác định "
    "ưu tiên điều tra và escalation. Các hạn mức trong portfolio là dữ liệu mô phỏng."
)

store = create_store(
    local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db"))
)
try:
    snap = build_risk_snapshot(store)
finally:
    store.close()

base = base_limit_control_table(snap)
stress = stress_control_table(snap)
summary = control_room_summary(snap)
queue = action_queue(snap)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Vượt hạn mức hiện tại", summary["base_breach_count"])
k2.metric("Cần theo dõi hiện tại", summary["base_attention_count"])
k3.metric(
    "Vượt hạn mức đầu tiên dưới stress",
    summary["first_stress_breach_scenario"] or "Chưa có",
)
k4.metric(
    "Số kiểm soát vượt ở stress cao nhất",
    summary["max_stress_breach_count"],
)

if (
    summary["base_breach_count"] == 0
    and summary["first_stress_breach_scenario"] is not None
):
    st.warning(
        "Trạng thái cơ sở chưa vượt hạn mức, nhưng stress testing đã xuất hiện breach. "
        "Ưu tiên đánh giá khả năng giảm exposure và phương án contingency trước khi điều kiện thị trường xấu đi."
    )
elif summary["base_breach_count"] > 0:
    st.error(
        "Đang có hạn mức bị vượt ở trạng thái cơ sở. Cần xác nhận dữ liệu, mở exception và escalation theo quy trình."
    )

st.markdown("### Nhận định quản trị")
for insight in management_insights(snap):
    st.markdown(f"- {insight}")

st.markdown("### Ưu tiên xử lý")
if queue.empty:
    st.success("Không có chỉ tiêu cần ưu tiên xử lý tại thời điểm hiện tại.")
else:
    queue_display = queue.rename(
        columns={
            "priority": "Ưu tiên",
            "issue": "Vấn đề",
            "trigger": "Ngưỡng kích hoạt",
            "action": "Hành động đề xuất",
            "source": "Nguồn",
        }
    )
    st.dataframe(queue_display, width="stretch", hide_index=True)

st.markdown("### Hạn mức hiện tại")
base_display = base.copy()
base_display["Chỉ tiêu"] = base_display["metric_id"].astype(str).map(
    METRIC_VI
).fillna(base_display["control_name"])
base_display["Trạng thái"] = (
    base_display["status"].astype(str).map(STATUS_VI).fillna(base_display["status"])
)
base_display = base_display.rename(
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
st.dataframe(base_display, width="stretch", hide_index=True)

st.markdown("### Stress theo kịch bản")
if stress.empty:
    st.info("Chưa có dữ liệu stress.")
else:
    compact = stress.rename(
        columns={
            "scenario_label": "Kịch bản",
            "shock_summary": "Cú sốc",
            "market_loss_bn_vnd": "Market loss (tỷ VND)",
            "max_utilization_pct": "Mức sử dụng cao nhất (%)",
            "breach_count": "Số kiểm soát vượt",
            "conclusion": "Kết luận",
        }
    )[[
        "Kịch bản",
        "Cú sốc",
        "Market loss (tỷ VND)",
        "Mức sử dụng cao nhất (%)",
        "Số kiểm soát vượt",
        "Kết luận",
    ]]
    st.dataframe(compact, width="stretch", hide_index=True)

    first = stress[stress["breach_count"] > 0]
    if not first.empty:
        row = first.iloc[0]
        st.error(
            f"Vượt hạn mức bắt đầu từ **{row['scenario_label']}**. "
            f"Mức sử dụng cao nhất trong kịch bản này là "
            f"{float(row['max_utilization_pct']):.1f}%."
        )

    with st.expander("Chi tiết mức sử dụng hạn mức theo stress"):
        detail = stress.rename(
            columns={
                "scenario_label": "Kịch bản",
                "fx_utilization_pct": "FX (%)",
                "rates_utilization_pct": "Lãi suất (%)",
                "liq_7d_utilization_pct": "Thanh khoản 7D (%)",
                "liq_30d_utilization_pct": "Thanh khoản 30D (%)",
            }
        )[[
            "Kịch bản",
            "FX (%)",
            "Lãi suất (%)",
            "Thanh khoản 7D (%)",
            "Thanh khoản 30D (%)",
        ]]
        st.dataframe(detail, width="stretch", hide_index=True)

st.caption(
    "Market loss là tổng tổn thất FX + lãi suất trong mô phỏng vì cùng đơn vị P&L. "
    "Liquidity GAP được đánh giá riêng theo hạn mức dòng tiền."
)

with st.expander("Ngưỡng cảnh báo & cách đọc"):
    st.markdown(
        """
- **BÌNH THƯỜNG:** dưới 80% hạn mức.
- **THEO DÕI:** từ 80% đến dưới 90%.
- **CẢNH BÁO:** từ 90% đến 100%.
- **VƯỢT HẠN MỨC:** trên 100%.

**Trạng thái cơ sở** dùng exposure hiện tại. **Stress testing** áp các cú sốc FX, lãi suất và dòng tiền ra rồi tính lại mức sử dụng hạn mức. Các ngưỡng và hạn mức trong trang này là framework mô phỏng của portfolio.
        """
    )
