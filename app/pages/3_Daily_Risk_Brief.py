from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.reporting.daily_brief import build_daily_risk_brief
from src.storage.factory import create_store
from src.ui.display import render_sidebar

st.set_page_config(page_title="Bản tin Rủi ro Ngày", layout="wide")
render_sidebar()
st.title("Bản tin Rủi ro Ngày")
st.caption("Bản tin giám sát deterministic từ dữ liệu công khai; không cần gọi OpenAI API để tạo báo cáo.")

try:
    store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
except Exception as exc:
    st.error(f"Không thể kết nối cơ sở dữ liệu: {type(exc).__name__}: {exc}")
    st.stop()

try:
    brief = build_daily_risk_brief(store)
    st.markdown(brief)
    filename = f"ban-tin-rui-ro-{datetime.now(timezone.utc).date().isoformat()}.md"
    st.download_button("Tải bản Markdown", data=brief.encode("utf-8"), file_name=filename, mime="text/markdown")
finally:
    store.close()
