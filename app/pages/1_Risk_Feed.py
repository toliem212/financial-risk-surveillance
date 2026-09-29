from __future__ import annotations

import os
from pathlib import Path
import sys

# Make repository root importable on local Windows and Streamlit Cloud.
_REPO_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import pandas as pd
import streamlit as st

from src.ai.client import AIService, AIDisabled, AIBudgetExceeded, AIInputTooLarge
from src.ai.investigation import generate_ai_investigation
from src.ai.policy import AIPolicy
from src.investigation.risk_feed import build_investigation_case, build_risk_feed
from src.storage.factory import create_store
from src.ui.display import domain_label, localize_dataframe, render_sidebar, severity_label, title_label

st.set_page_config(page_title="Dòng rủi ro & Điều tra", layout="wide")
render_sidebar()
st.title("Dòng Rủi ro Liên thị trường & Điều tra")
st.caption("Giám sát rule-based cho Thanh khoản, FX, Lãi suất/TPCP, TPDN và Chất lượng dữ liệu. Các kênh truyền dẫn chỉ là bối cảnh phân tích, không phải kết luận nhân quả.")


def _store():
    return create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))


def _fmt(item: dict) -> str:
    entity = f" · {item['entity_id']}" if item.get("entity_id") else ""
    return f"[{severity_label(item['severity'])}] {domain_label(item['domain'])} · {title_label(item['title'])}{entity} · {item['timestamp']}"


try:
    store = _store()
except Exception as exc:
    st.error(f"Không thể kết nối cơ sở dữ liệu: {type(exc).__name__}: {exc}")
    st.stop()

try:
    feed = build_risk_feed(store, limit=250)
    if not feed:
        st.info("Chưa có mục nào trong Risk Feed. Hãy chạy ingestion trước.")
        st.stop()

    feed_df = pd.DataFrame(feed)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Số mục trong Feed", len(feed_df))
    c2.metric("HIGH/CRITICAL", int(feed_df["severity"].isin(["HIGH", "CRITICAL"]).sum()))
    c3.metric("Số nhóm rủi ro", int(feed_df["domain"].nunique()))
    c4.metric("Lifecycle event mức INFO", int(((feed_df["item_type"] == "EVENT") & (feed_df["severity"] == "INFO")).sum()))

    st.subheader("Dòng rủi ro (Risk Feed)")
    visible = [c for c in ["timestamp", "severity", "domain", "item_type", "title", "entity_id", "source"] if c in feed_df.columns]
    st.dataframe(localize_dataframe(feed_df[visible]), width="stretch", hide_index=True)

    signal_items = [x for x in feed if x.get("signal_id")]
    if not signal_items:
        st.info("Feed hiện chỉ có lifecycle event; chưa có deterministic signal để điều tra.")
        st.stop()

    st.subheader("Điều tra cảnh báo (Investigation)")
    selected = st.selectbox("Chọn một deterministic signal", signal_items, format_func=_fmt)
    case = build_investigation_case(store, selected["signal_id"])
    s = case.signal

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Mức độ", severity_label(s.get("severity") or "—"))
    q2.metric("Nhóm", domain_label(s.get("domain") or "—"))
    q3.metric("Đối tượng", s.get("entity_id") or "—")
    q4.metric("Chất lượng dữ liệu", case.data_quality.get("status") or "—")

    st.markdown("### Điều gì vừa thay đổi?")
    st.write(title_label(selected["title"]))
    values = {
        "Giá trị hiện tại": s.get("current_value"),
        "Mức tham chiếu": s.get("baseline_value"),
        "Thay đổi tuyệt đối": s.get("absolute_change"),
        "Thay đổi tương đối": s.get("relative_change"),
        "Ngưỡng": s.get("threshold"),
    }
    st.json({k: v for k, v in values.items() if v is not None})

    st.markdown("### Bằng chứng (Evidence)")
    st.json(case.evidence)

    st.markdown("### Chất lượng dữ liệu")
    st.json(case.data_quality)

    st.markdown("### Quan sát thị trường công khai liên quan")
    if case.related_observations:
        rel = pd.DataFrame(case.related_observations)
        cols = [c for c in ["period_end", "metric_id", "entity_id", "value", "unit", "source", "quality_flag", "observation_method"] if c in rel.columns]
        st.dataframe(localize_dataframe(rel[cols]), width="stretch", hide_index=True)
    else:
        st.info("Không có quan sát liên quan trong cửa sổ dữ liệu hiện tại.")

    st.markdown("### Bối cảnh lịch sử")
    st.json(case.historical_context)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Kênh truyền dẫn rủi ro có thể xảy ra")
        for line in case.possible_risk_transmission:
            st.markdown(f"- {line}")
    with c2:
        st.markdown("### Cần theo dõi tiếp")
        for line in case.monitor_next:
            st.markdown(f"- {line}")

    st.info("Trang này chỉ diễn giải bằng chứng từ dữ liệu thị trường công khai. Hệ thống **không suy đoán** vị thế, hạn mức, P&L hay mức độ phơi nhiễm nội bộ của bất kỳ tổ chức nào.")

    st.markdown("### AI Investigation — tùy chọn")
    policy = AIPolicy.from_env()
    if not policy.enabled:
        st.caption("AI mặc định đang TẮT. Chỉ bật AI_ENABLED=1 và OPENAI_API_KEY khi chủ động muốn dùng; deterministic surveillance vẫn hoạt động đầy đủ khi không có AI.")
    else:
        st.caption(f"Model: {policy.model} · giới hạn API/ngày: {policy.daily_call_limit} · output cap: {policy.investigation_max_output_tokens} tokens")
        if st.button("Phân tích signal đã chọn bằng AI", type="secondary"):
            try:
                result = generate_ai_investigation(AIService(store, policy=policy), case)
                st.session_state["ai_investigation_result"] = result
            except (AIDisabled, AIBudgetExceeded, AIInputTooLarge) as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(f"Yêu cầu AI thất bại: {type(exc).__name__}: {exc}")

        result = st.session_state.get("ai_investigation_result")
        if result is not None:
            meta = "cache hit" if result.cached else f"API call · {result.total_tokens} tokens"
            st.caption(f"{meta} · model {result.model}")
            data = result.data
            st.markdown(f"**Tóm tắt:** {data.get('summary','')}")
            st.markdown(f"**Điều gì thay đổi:** {data.get('what_changed','')}")
            st.markdown(f"**Vì sao đáng chú ý:** {data.get('why_it_matters','')}")
            st.markdown(f"**Chất lượng dữ liệu:** {data.get('data_quality_note','')}")
            c3, c4 = st.columns(2)
            with c3:
                st.markdown("**Kênh truyền dẫn có thể xảy ra**")
                for line in data.get("possible_transmission", []):
                    st.markdown(f"- {line}")
            with c4:
                st.markdown("**Theo dõi tiếp**")
                for line in data.get("monitor_next", []):
                    st.markdown(f"- {line}")
            if data.get("caveats"):
                st.markdown("**Lưu ý/giới hạn**")
                for line in data["caveats"]:
                    st.markdown(f"- {line}")
finally:
    store.close()
