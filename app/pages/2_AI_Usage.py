from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from src.ai.policy import AIPolicy
from src.storage.factory import create_store
from src.ui.display import localize_dataframe, render_sidebar

st.set_page_config(page_title="Sử dụng AI & Ngân sách", layout="wide")
render_sidebar()
st.title("Sử dụng AI & Ngân sách")
st.caption("Guardrail vận hành cho lớp OpenAI tùy chọn. Deterministic surveillance không phụ thuộc AI.")

policy = AIPolicy.from_env()
st.write("Trạng thái AI:", "ĐANG BẬT" if policy.enabled else "TẮT")
st.write("Mô hình:", policy.model)
st.write("Giới hạn API call/ngày:", policy.daily_call_limit)
st.write("Giới hạn ký tự input/request:", policy.max_input_chars)

store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
try:
    today = datetime.now(timezone.utc).date().isoformat() + "T00:00:00+00:00"
    month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily = store.ai_usage_summary(today)
    monthly = store.ai_usage_summary(month)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("API call hôm nay", int(daily.get("api_calls") or 0))
    c2.metric("Cache hit hôm nay", int(daily.get("cache_hits") or 0))
    c3.metric("Tokens tháng này", int(monthly.get("total_tokens") or 0))
    est = monthly.get("estimated_cost_usd")
    c4.metric("Chi phí API ước tính tháng", "chưa cấu hình" if est is None else f"${float(est):.4f}")

    if not any((policy.input_usd_per_mtok, policy.cached_input_usd_per_mtok, policy.output_usd_per_mtok)):
        st.info("Hệ thống vẫn audit token usage. Ước tính chi phí chỉ được bật khi nhập giá model hiện hành qua các biến AI_*_USD_PER_MTOK.")

    rows = store.recent_ai_usage(100)
    if rows:
        df = pd.DataFrame(rows)
        cols = [c for c in ["created_at", "feature", "model", "cached_hit", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd", "status"] if c in df.columns]
        st.dataframe(localize_dataframe(df[cols]), width="stretch", hide_index=True)
    else:
        st.info("Chưa có lần sử dụng AI nào. Đây là trạng thái bình thường khi AI_ENABLED=0.")
finally:
    store.close()
