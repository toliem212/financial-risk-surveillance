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
from src.risk_core.var_es import build_var_es_report
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
    var_es_report = build_var_es_report(store, snap)
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

st.subheader("VaR / ES — Rủi ro lãi suất TPCP")

status_label = {
    "READY": "SẴN SÀNG",
    "INDICATIVE": "THAM KHẢO",
    "NOT_READY": "CHƯA ĐỦ DỮ LIỆU",
}

rates_hit = var_es_report[var_es_report["risk_scope"].astype(str).eq("Rates / TPCP")]
fx_hit = var_es_report[var_es_report["risk_scope"].astype(str).eq("FX / USD-VND")]
combined_hit = var_es_report[var_es_report["risk_scope"].astype(str).eq("Combined market risk")]

if rates_hit.empty:
    st.warning("Chưa có đủ dữ liệu để lập báo cáo VaR / ES cho danh mục TPCP.")
else:
    rates = rates_hit.iloc[0]

    sessions = int(rates.get("sessions") or 0)
    pnl_obs = int(rates.get("pnl_observations") or 0)
    minimum = int(rates.get("minimum_required") or 250)
    dq_excluded = int(rates.get("dq_excluded") or 0)
    state = str(rates.get("status") or "NOT_READY")
    progress = min(1.0, pnl_obs / minimum) if minimum > 0 else 0.0

    hist_var = rates.get("historical_var_99_bn")
    es975 = rates.get("expected_shortfall_97_5_bn")
    es99 = rates.get("expected_shortfall_99_bn")
    param_var = rates.get("parametric_var_99_bn")

    st.caption(
        "Phạm vi tính: chuỗi lợi suất TPCP HNX lịch sử kết hợp với danh mục TPCP mô phỏng "
        "và PV01 hiện tại. Đơn vị rủi ro: tỷ VND, kỳ nắm giữ 1 ngày."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "VaR lịch sử 99%",
        "N/A" if pd.isna(hist_var) else f"{float(hist_var):,.2f} tỷ",
        help="Ngưỡng lỗ 1 ngày ước tính từ phân phối P&L lịch sử ở mức tin cậy 99%.",
    )
    c2.metric(
        "ES 97,5%",
        "N/A" if pd.isna(es975) else f"{float(es975):,.2f} tỷ",
        help="Mức lỗ trung bình của các quan sát nằm ngoài ngưỡng VaR 97,5%.",
    )
    c3.metric(
        "ES 99%",
        "N/A" if pd.isna(es99) else f"{float(es99):,.2f} tỷ",
        help="Mức lỗ trung bình của phần đuôi xấu nhất 1% trong mẫu lịch sử.",
    )
    c4.metric(
        "VaR tham số 99%",
        "N/A" if pd.isna(param_var) else f"{float(param_var):,.2f} tỷ",
        help="VaR 1 ngày theo độ lệch chuẩn P&L và giả định phân phối chuẩn.",
    )

    st.markdown(f"**Mức độ hoàn thiện dữ liệu: {pnl_obs}/{minimum} quan sát P&L hợp lệ ({progress:.0%}) · {status_label.get(state, state)}**")
    st.progress(progress)

    if state == "INDICATIVE":
        st.info(
            f"Hiện có {pnl_obs} quan sát P&L hợp lệ, tương đương {progress:.0%} mốc 250 phiên. "
            f"Kết quả VaR/ES được sử dụng ở mức tham khảo cho giám sát; cần thêm "
            f"{max(0, minimum - pnl_obs)} quan sát để chuyển sang trạng thái Sẵn sàng."
        )
    elif state == "READY":
        st.success(
            f"Chuỗi có {pnl_obs} quan sát P&L hợp lệ và đã đạt mốc dữ liệu 250 phiên."
        )
    else:
        st.info(
            f"Chuỗi hiện có {pnl_obs} quan sát P&L hợp lệ. Tiếp tục tích lũy lịch sử trước khi "
            f"đưa VaR/ES vào phần giám sát chính."
        )

    insight_lines = []
    if pd.notna(hist_var) and pd.notna(param_var) and float(param_var) > 0:
        diff = float(hist_var) - float(param_var)
        pct = abs(diff) / float(param_var) * 100.0
        if diff > 0:
            insight_lines.append(
                f"VaR lịch sử cao hơn VaR tham số **{abs(diff):,.2f} tỷ VND ({pct:.1f}%)**. "
                "Trong mẫu hiện tại, phân phối P&L thực tế cho mức lỗ đuôi lớn hơn kết quả từ giả định phân phối chuẩn."
            )
        elif diff < 0:
            insight_lines.append(
                f"VaR lịch sử thấp hơn VaR tham số **{abs(diff):,.2f} tỷ VND ({pct:.1f}%)**. "
                "Trong mẫu hiện tại, mô hình phân phối chuẩn cho mức rủi ro cao hơn phân phối P&L quan sát được."
            )

    if pd.notna(es99) and pd.notna(hist_var) and float(hist_var) > 0:
        tail_gap = float(es99) - float(hist_var)
        tail_pct = tail_gap / float(hist_var) * 100.0
        if tail_gap > 0:
            insight_lines.append(
                f"ES 99% cao hơn VaR lịch sử 99% **{tail_gap:,.2f} tỷ VND ({tail_pct:.1f}%)**. "
                "Khi tổn thất vượt ngưỡng VaR, mức lỗ trung bình ở phần đuôi vẫn tăng đáng kể."
            )

    if dq_excluded > 0:
        insight_lines.append(
            f"Data Quality Gate đã loại **{dq_excluded} phiên** có biến động lợi suất vượt ngưỡng kiểm soát dữ liệu "
            "khỏi mẫu VaR để rà soát trước khi ước lượng."
        )

    st.caption(
        "Cách đọc nhanh: VaR 99% cho biết ngưỡng tổn thất ước tính trong 1 ngày; "
        "ES 99% cho biết mức tổn thất trung bình khi danh mục rơi vào 1% kịch bản xấu nhất. "
        "ES 97,5% bổ sung góc nhìn về rủi ro phần đuôi ở một mức tin cậy khác."
    )

    if insight_lines:
        st.markdown("#### Nhận định chính")
        st.markdown("\n".join(f"- {line}" for line in insight_lines))

    if pd.notna(es99) and pnl_obs > 0:
        tail_count = max(1, int(round(pnl_obs * 0.01)))
        st.caption(
            f"Lưu ý khi đọc ES 99%: với {pnl_obs} quan sát, phần đuôi 1% chỉ tương ứng khoảng "
            f"{tail_count}–{tail_count + 1} phiên. Chỉ số này sẽ còn nhạy khi dữ liệu lịch sử được bổ sung."
        )

    bt_obs = int(rates.get("backtest_observations") or 0)
    bt_exc = int(rates.get("backtest_exceptions") or 0)
    bt_rate = rates.get("backtest_exception_rate_pct")

    st.markdown("#### Backtesting")
    if bt_obs <= 0:
        st.write(
            "Chưa có kết quả backtest 250 phiên. Cần đủ một cửa sổ 250 quan sát để ước lượng VaR "
            "và thêm dữ liệu ngoài mẫu để kiểm định số lần vượt VaR."
        )
    else:
        bt_rate_text = "N/A" if pd.isna(bt_rate) else f"{float(bt_rate):.2f}%"
        b1, b2, b3 = st.columns(3)
        b1.metric("Số phiên backtest", f"{bt_obs:,}")
        b2.metric("Số lần vượt VaR", f"{bt_exc:,}")
        b3.metric("Tỷ lệ vượt VaR", bt_rate_text)

with st.expander("Chi tiết độ phủ dữ liệu"):
    detail = var_es_report.copy()
    detail["Trạng thái"] = detail["status"].astype(str).map(status_label).fillna(detail["status"])
    detail = detail.rename(
        columns={
            "risk_scope": "Phạm vi rủi ro",
            "sessions": "Phiên dữ liệu",
            "pnl_observations": "P&L hợp lệ",
            "minimum_required": "Mốc tham chiếu",
            "dq_excluded": "DQ loại",
            "backtest_observations": "Phiên backtest",
        }
    )
    display_cols = [
        "Phạm vi rủi ro",
        "Phiên dữ liệu",
        "P&L hợp lệ",
        "Mốc tham chiếu",
        "Trạng thái",
        "DQ loại",
        "Phiên backtest",
    ]
    st.dataframe(detail[display_cols], width="stretch", hide_index=True)

    if not fx_hit.empty:
        fx = fx_hit.iloc[0]
        fx_obs = int(fx.get("pnl_observations") or 0)
        st.caption(
            f"USD/VND hiện có {fx_obs} quan sát P&L lịch sử. VaR cho FX và Combined Market Risk "
            "sẽ được bổ sung khi chuỗi tỷ giá tích lũy đủ dữ liệu."
        )
