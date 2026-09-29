from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.ui.dataframe import make_arrow_safe

COLUMN_LABELS = {
    "timestamp": "Thời điểm",
    "generated_at": "Thời điểm tạo",
    "started_at": "Bắt đầu",
    "finished_at": "Kết thúc",
    "period_start": "Đầu kỳ",
    "period_end": "Cuối kỳ",
    "event_date": "Ngày sự kiện",
    "announced_at": "Thời điểm công bố",
    "first_observed_at": "Lần đầu hệ thống ghi nhận",
    "source_published_at": "Nguồn công bố lúc",
    "fetched_at": "Thu thập lúc",
    "severity": "Mức độ",
    "domain": "Nhóm rủi ro",
    "item_type": "Loại mục",
    "title": "Nội dung",
    "entity_id": "Đối tượng",
    "issuer_id": "Tổ chức phát hành",
    "bond_id": "Trái phiếu",
    "source": "Nguồn",
    "source_url": "URL nguồn",
    "worker": "Tiến trình",
    "status": "Trạng thái",
    "records_new": "Bản ghi mới",
    "records_invalid": "Bản ghi lỗi",
    "error_type": "Loại lỗi",
    "error_message": "Chi tiết lỗi",
    "age_minutes": "Độ trễ (phút)",
    "metric_id": "Chỉ tiêu",
    "value": "Giá trị",
    "unit": "Đơn vị",
    "quality_flag": "Chất lượng",
    "observation_method": "Phương pháp quan sát",
    "measure_type": "Bản chất dữ liệu",
    "frequency": "Tần suất",
    "signal_type": "Loại cảnh báo",
    "current_value": "Giá trị hiện tại",
    "baseline_value": "Mức tham chiếu",
    "absolute_change": "Thay đổi tuyệt đối",
    "relative_change": "Thay đổi tương đối",
    "threshold": "Ngưỡng",
    "event_type": "Loại sự kiện",
    "trading_code": "Mã giao dịch",
    "disclosure_code": "Mã CBTT",
    "issuer_name": "Tổ chức phát hành",
    "registration_status": "Trạng thái ĐKGD",
    "first_trade_date": "Ngày GD đầu tiên",
    "last_seen_at": "Ghi nhận gần nhất",
    "tenor": "Kỳ hạn",
    "tenor_years": "Kỳ hạn (năm)",
    "created_at": "Thời điểm",
    "feature": "Tính năng AI",
    "model": "Mô hình",
    "cached_hit": "Cache hit",
    "input_tokens": "Input tokens",
    "cached_input_tokens": "Cached input tokens",
    "output_tokens": "Output tokens",
    "total_tokens": "Tổng tokens",
    "estimated_cost_usd": "Chi phí ước tính (USD)",
    "kind": "Loại",
    "label": "Nhãn",
}

DOMAIN_LABELS = {
    "LIQUIDITY": "Thanh khoản (LIQUIDITY)",
    "FX": "Ngoại hối (FX)",
    "RATES": "Lãi suất/TPCP (RATES)",
    "CORPORATE_BOND": "Trái phiếu DN (CORPORATE_BOND)",
    "DATA_QUALITY": "Chất lượng dữ liệu (DATA_QUALITY)",
    "OTHER": "Khác (OTHER)",
}
SEVERITY_LABELS = {
    "INFO": "Thông tin (INFO)",
    "LOW": "Thấp (LOW)",
    "MEDIUM": "Trung bình (MEDIUM)",
    "HIGH": "Cao (HIGH)",
    "CRITICAL": "Nghiêm trọng (CRITICAL)",
}
ITEM_LABELS = {"SIGNAL": "Cảnh báo (SIGNAL)", "EVENT": "Sự kiện (EVENT)"}
STATUS_LABELS = {
    "SUCCESS": "Thành công (SUCCESS)",
    "SUCCESS_WITH_INVALID": "Thành công, có bản ghi lỗi",
    "FAILED": "Thất bại (FAILED)",
    "RUNNING": "Đang chạy (RUNNING)",
    "OPEN": "Đang mở (OPEN)",
    "CLOSED": "Đã đóng (CLOSED)",
}
TITLE_LABELS = {
    "Payment Delay": "Chậm thanh toán (Payment Delay)",
    "Maturity Extension": "Gia hạn kỳ hạn (Maturity Extension)",
    "Collateral Change": "Thay đổi tài sản bảo đảm (Collateral Change)",
    "Term Change": "Thay đổi điều khoản (Term Change)",
    "Trading Suspension": "Tạm ngừng giao dịch (Trading Suspension)",
    "Delisting": "Hủy đăng ký giao dịch (Delisting)",
    "Registration": "Đăng ký giao dịch (Registration)",
    "Rating Observation": "Cập nhật xếp hạng tín nhiệm (Rating Observation)",
    "Early Redemption": "Mua lại trước hạn (Early Redemption)",
    "OMO rate changed materially": "Lãi suất OMO biến động đáng kể",
    "OMO volume changed materially": "Khối lượng OMO biến động đáng kể",
    "Government-bond yield moved materially": "Lợi suất TPCP biến động đáng kể",
    "Government-bond curve steepened": "Đường cong lợi suất TPCP dốc lên",
    "Government-bond curve flattened": "Đường cong lợi suất TPCP phẳng hơn",
    "USD/VND interbank move is elevated": "USD/VND liên ngân hàng biến động mạnh",
    "USD/VND is close to an SBV policy reference": "USD/VND tiến gần mức tham chiếu điều hành của NHNN",
    "Public-source reconciliation mismatch": "Sai lệch khi đối chiếu nguồn công khai",
}


def localize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if "domain" in out.columns:
        out["domain"] = out["domain"].map(lambda x: DOMAIN_LABELS.get(str(x), x))
    if "severity" in out.columns:
        out["severity"] = out["severity"].map(lambda x: SEVERITY_LABELS.get(str(x), x))
    if "item_type" in out.columns:
        out["item_type"] = out["item_type"].map(lambda x: ITEM_LABELS.get(str(x), x))
    if "status" in out.columns:
        out["status"] = out["status"].map(lambda x: STATUS_LABELS.get(str(x), x))
    if "title" in out.columns:
        out["title"] = out["title"].map(lambda x: TITLE_LABELS.get(str(x), x))
    out = out.rename(columns={c: COLUMN_LABELS.get(c, c) for c in out.columns})
    return make_arrow_safe(out)


def domain_label(value: Any) -> str:
    return DOMAIN_LABELS.get(str(value), str(value))


def severity_label(value: Any) -> str:
    return SEVERITY_LABELS.get(str(value), str(value))


def title_label(value: Any) -> str:
    return TITLE_LABELS.get(str(value), str(value))


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### Điều hướng")
        st.page_link("Home.py", label="🏠 Tổng quan")
        st.page_link("pages/1_Risk_Feed.py", label="🚨 Dòng rủi ro & Điều tra")
        st.page_link("pages/3_Daily_Risk_Brief.py", label="📝 Bản tin rủi ro ngày")
        st.page_link("pages/7_Historical_Replay.py", label="⏪ Tái dựng lịch sử")
        st.page_link("pages/2_AI_Usage.py", label="🤖 Sử dụng AI & Ngân sách")
        st.page_link("pages/8_Methodology.py", label="📚 Phương pháp & Giới hạn")
        st.divider()
        mode = os.getenv("APP_DATA_MODE", "LIVE").strip().upper() or "LIVE"
        if mode == "DEMO":
            st.warning("**DEMO** — dữ liệu mô phỏng/fixture, không phải dữ liệu thị trường live.")
        else:
            backend = "CLOUD / PostgreSQL" if os.getenv("DATABASE_URL", "").strip() else "LOCAL / SQLite"
            st.success(f"**LIVE** — backend: {backend}")
