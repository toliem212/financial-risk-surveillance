from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd
import streamlit as st

from src.ai.client import AIService, AIDisabled, AIBudgetExceeded, AIInputTooLarge
from src.ai.investigation import generate_ai_investigation
from src.ai.policy import AIPolicy
from src.investigation.case_management import (
    DOMAIN_VI,
    DQ_VI,
    STATUS_VI,
    case_priority,
    case_workflow,
    compact_related_observations,
    escalation_guidance,
    feed_summary,
    latest_feed_view,
    next_actions,
    signal_value_table,
)
from src.investigation.risk_feed import build_investigation_case, build_risk_feed
from src.storage.factory import create_store
from src.ui.display import domain_label, severity_label, title_label, render_sidebar

st.set_page_config(page_title="Risk Feed & Investigation", layout="wide")
render_sidebar()

st.title("Risk Feed & Investigation")
st.caption(
    "Từ tín hiệu rule-based tới xác minh dữ liệu, rà soát driver, hành động và escalation. "
    "AI chỉ là lớp enrichment tùy chọn; workflow cốt lõi không phụ thuộc AI."
)


def _store():
    return create_store(
        local_db_path=Path(
            os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")
        )
    )


def _fmt(item: dict) -> str:
    entity = f" · {item['entity_id']}" if item.get("entity_id") else ""
    return (
        f"[{severity_label(item['severity'])}] "
        f"{domain_label(item['domain'])} · "
        f"{title_label(item['title'])}{entity} · "
        f"{item['timestamp']}"
    )


try:
    store = _store()
except Exception as exc:
    st.error(
        f"Không thể kết nối cơ sở dữ liệu: "
        f"{type(exc).__name__}: {exc}"
    )
    st.stop()

try:
    feed = build_risk_feed(store, signal_limit=500, event_limit=300, limit=800)
    if not feed:
        st.info("Chưa có mục nào trong Risk Feed. Hãy chạy ingestion trước.")
        st.stop()

    current_feed = latest_feed_view(feed)
    current_summary = feed_summary(current_feed)
    history_summary = feed_summary(feed)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Signal hiện tại", current_summary["signals"])
    k2.metric("HIGH / CRITICAL", current_summary["high_critical"])
    k3.metric("Nhóm rủi ro", current_summary["domains"])
    k4.metric("Signal lịch sử", history_summary["signals"])

    st.markdown("### Risk Feed")
    show_history = st.toggle(
        "Hiển thị toàn bộ lịch sử signal / event",
        value=False,
        help="Mặc định feed chỉ giữ quan sát mới nhất cho từng loại signal và đối tượng để tránh lặp cảnh báo lịch sử.",
    )
    active_feed = feed if show_history else current_feed
    feed_df = pd.DataFrame(active_feed)

    f1, f2, f3 = st.columns(3)
    with f1:
        severity_options = sorted(
            feed_df["severity"].dropna().astype(str).unique().tolist()
        )
        severity_filter = st.multiselect(
            "Mức độ",
            severity_options,
            default=severity_options,
        )
    with f2:
        domain_options = sorted(
            feed_df["domain"].dropna().astype(str).unique().tolist()
        )
        domain_filter = st.multiselect(
            "Nhóm rủi ro",
            domain_options,
            default=domain_options,
            format_func=lambda x: DOMAIN_VI.get(x, domain_label(x)),
        )
    with f3:
        type_options = sorted(
            feed_df["item_type"].dropna().astype(str).unique().tolist()
        )
        type_filter = st.multiselect(
            "Loại",
            type_options,
            default=type_options,
        )

    filtered = feed_df[
        feed_df["severity"].astype(str).isin(severity_filter)
        & feed_df["domain"].astype(str).isin(domain_filter)
        & feed_df["item_type"].astype(str).isin(type_filter)
    ].copy()

    if filtered.empty:
        st.info("Không có mục nào phù hợp bộ lọc.")
    else:
        visible = [
            c
            for c in [
                "timestamp",
                "event_date",
                "severity",
                "domain",
                "item_type",
                "title",
                "entity_id",
                "source",
                "status",
            ]
            if c in filtered.columns
        ]
        display = filtered[visible].rename(
            columns={
                "timestamp": "Ngày quan sát",
                "event_date": "Ngày sự kiện",
                "severity": "Mức độ",
                "domain": "Nhóm",
                "item_type": "Loại",
                "title": "Tín hiệu / sự kiện",
                "entity_id": "Đối tượng",
                "source": "Nguồn",
                "status": "Trạng thái",
            }
        )
        display["Nhóm"] = display["Nhóm"].map(
            lambda x: DOMAIN_VI.get(str(x), str(x))
        )
        display["Tín hiệu / sự kiện"] = display[
            "Tín hiệu / sự kiện"
        ].map(title_label)
        if "Ngày sự kiện" in display.columns:
            display["Ngày sự kiện"] = display["Ngày sự kiện"].map(
                lambda x: "—" if pd.isna(x) or x in {None, ""} else str(x)
            )
        if "Trạng thái" in display.columns:
            display["Trạng thái"] = display["Trạng thái"].map(
                lambda x: (
                    "—"
                    if pd.isna(x) or x in {None, "", "None"}
                    else STATUS_VI.get(str(x).upper(), str(x))
                )
            )
        st.dataframe(display, width="stretch", hide_index=True)

    signal_items = [x for x in active_feed if x.get("signal_id")]
    if not signal_items:
        st.info(
            "Feed hiện chỉ có lifecycle event; chưa có deterministic signal để điều tra."
        )
        st.stop()

    st.markdown("---")
    st.markdown("## Investigation Case")

    selected = st.selectbox(
        "Chọn signal để rà soát",
        signal_items,
        format_func=_fmt,
    )
    case = build_investigation_case(store, selected["signal_id"])
    signal = case.signal
    priority = case_priority(case)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ưu tiên", priority["priority"])
    c2.metric("Mức độ", priority["severity_vi"])
    c3.metric("Data Quality", priority["dq_vi"])
    c4.metric(
        "Trạng thái",
        STATUS_VI.get(
            str(signal.get("status") or "OPEN").upper(),
            str(signal.get("status") or "OPEN"),
        ),
    )
    st.caption(
        f"Nhóm: **{DOMAIN_VI.get(str(signal.get('domain') or ''), str(signal.get('domain') or '—'))}**"
        f" · Đối tượng: **{signal.get('entity_id') or '—'}**"
        f" · Ngày dữ liệu: **{selected.get('timestamp') or '—'}**"
    )

    st.info(priority["rationale"])

    st.markdown("### Workflow điều tra")
    workflow = pd.DataFrame(case_workflow(case))
    workflow = workflow.rename(
        columns={
            "step": "Bước",
            "state": "Trạng thái",
            "detail": "Nội dung",
        }
    )
    st.dataframe(workflow, width="stretch", hide_index=True)

    st.markdown("### 1. Signal vừa thay đổi gì?")
    values = signal_value_table(case)
    if values.empty:
        st.caption("Signal không có bộ current/baseline/change dạng số.")
    else:
        st.dataframe(values, width="stretch", hide_index=True)

    st.markdown("### 2. Xác minh dữ liệu")
    dq1, dq2, dq3 = st.columns(3)
    dq1.metric(
        "Kết luận DQ",
        DQ_VI.get(
            str(case.data_quality.get("status") or "OK").upper(),
            str(case.data_quality.get("status") or "—"),
        ),
    )
    dq2.metric(
        "Số quan sát cần chú ý",
        int(case.data_quality.get("questionable_count") or 0),
    )
    flags = case.data_quality.get("flags_present") or []
    dq3.metric("Quality flags", ", ".join(flags) if flags else "Không có")

    with st.expander("Bằng chứng gốc của signal"):
        st.json(case.evidence)

    st.markdown("### 3. Driver & market context")
    hist = case.historical_context or {}
    hist_unit = str(hist.get("unit") or "")

    def _hist_value(key: str):
        value = hist.get(key)
        if value is None:
            return "—"
        try:
            return f"{float(value):,.4f}"
        except (TypeError, ValueError):
            return str(value)

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Số điểm lịch sử", int(hist.get("count") or 0))
    h2.metric("Min", _hist_value("min"))
    h3.metric("Max", _hist_value("max"))
    h4.metric("Latest", _hist_value("latest"))
    if hist_unit:
        st.caption(f"Đơn vị chuỗi lịch sử: {hist_unit}")

    related = compact_related_observations(case)
    if related.empty:
        st.caption("Chưa có quan sát thị trường liên quan để đối chiếu.")
    else:
        related = related.rename(
            columns={
                "period_end": "Ngày",
                "metric_id": "Metric",
                "entity_id": "Đối tượng",
                "value": "Giá trị",
                "unit": "Đơn vị",
                "source": "Nguồn",
                "quality_flag": "DQ",
                "observation_method": "Phương pháp",
            }
        )
        st.dataframe(related, width="stretch", hide_index=True)

    st.markdown("### 4. Kênh rủi ro & theo dõi tiếp")
    domain = str(signal.get("domain") or "OTHER").upper()
    from src.investigation.case_management import (
        MONITOR_NEXT_VI,
        TRANSMISSION_VI,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Kênh truyền dẫn có thể xảy ra**")
        for line in TRANSMISSION_VI.get(
            domain,
            ["Chưa cấu hình narrative cho nhóm rủi ro này."],
        ):
            st.markdown(f"- {line}")

    with right:
        st.markdown("**Cần theo dõi tiếp**")
        for line in MONITOR_NEXT_VI.get(
            domain,
            ["Theo dõi quan sát tiếp theo và chất lượng nguồn."],
        ):
            st.markdown(f"- {line}")

    st.markdown("### 5. Hành động & escalation")
    for action in next_actions(case):
        st.markdown(f"- {action}")
    st.warning(escalation_guidance(case))

    st.markdown("---")
    st.markdown("### AI Commentary · tùy chọn")

    policy = AIPolicy.from_env()
    if not policy.enabled:
        st.caption(
            "AI đang tắt. Deterministic investigation ở trên vẫn hoạt động đầy đủ."
        )
    else:
        st.caption(
            f"Model: {policy.model} · giới hạn API/ngày: "
            f"{policy.daily_call_limit} · output cap: "
            f"{policy.investigation_max_output_tokens} tokens"
        )
        if st.button(
            "Phân tích signal đã chọn bằng AI",
            type="secondary",
        ):
            try:
                result = generate_ai_investigation(
                    AIService(store, policy=policy),
                    case,
                )
                st.session_state["ai_investigation_result"] = result
            except (AIDisabled, AIBudgetExceeded, AIInputTooLarge) as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(
                    f"Yêu cầu AI thất bại: "
                    f"{type(exc).__name__}: {exc}"
                )

        result = st.session_state.get("ai_investigation_result")
        if result is not None:
            meta = (
                "cache hit"
                if result.cached
                else f"API call · {result.total_tokens} tokens"
            )
            st.caption(f"{meta} · model {result.model}")
            data = result.data
            st.markdown(f"**Tóm tắt:** {data.get('summary', '')}")
            st.markdown(
                f"**Điều gì thay đổi:** "
                f"{data.get('what_changed', '')}"
            )
            st.markdown(
                f"**Vì sao đáng chú ý:** "
                f"{data.get('why_it_matters', '')}"
            )
            st.markdown(
                f"**Chất lượng dữ liệu:** "
                f"{data.get('data_quality_note', '')}"
            )

            ai_left, ai_right = st.columns(2)
            with ai_left:
                st.markdown("**Kênh truyền dẫn có thể xảy ra**")
                for line in data.get("possible_transmission", []):
                    st.markdown(f"- {line}")
            with ai_right:
                st.markdown("**Theo dõi tiếp**")
                for line in data.get("monitor_next", []):
                    st.markdown(f"- {line}")

            if data.get("caveats"):
                st.markdown("**Lưu ý / giới hạn**")
                for line in data["caveats"]:
                    st.markdown(f"- {line}")
finally:
    store.close()
