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

from src.storage.factory import create_store
from src.ui.display import localize_dataframe, render_sidebar
from src.version import PROJECT_VERSION

st.set_page_config(page_title="Giám sát Rủi ro Tài chính Việt Nam", layout="wide")
render_sidebar()
st.title("Hệ thống Giám sát Rủi ro Tài chính Việt Nam")
st.caption(f"Vietnam Financial Risk Surveillance · {PROJECT_VERSION} · giám sát rủi ro từ dữ liệu công khai gần thời gian thực")

mode = os.getenv("APP_DATA_MODE", "LIVE").strip().upper() or "LIVE"
if mode == "DEMO":
    st.warning("Đang ở **CHẾ ĐỘ DEMO**: toàn bộ dữ liệu trên màn hình là fixture/mô phỏng để kiểm thử, không phải dữ liệu thị trường live.")
else:
    backend = "Supabase PostgreSQL" if os.getenv("DATABASE_URL", "").strip() else "SQLite local"
    st.info(f"Đang ở **CHẾ ĐỘ LIVE** · Backend: **{backend}**. Một nguồn lỗi được coi là dữ liệu thiếu/không khả dụng, không phải giá trị 0.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.page_link("pages/1_Risk_Feed.py", label="Dòng rủi ro", icon="🚨")
with c2:
    st.page_link("pages/3_Daily_Risk_Brief.py", label="Bản tin rủi ro ngày", icon="📝")
with c3:
    st.page_link("pages/7_Historical_Replay.py", label="Tái dựng lịch sử", icon="⏪")
with c4:
    st.page_link("pages/2_AI_Usage.py", label="Sử dụng AI", icon="🤖")


def _store():
    return create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))


def _df(rows):
    return pd.DataFrame(rows) if rows else pd.DataFrame()


try:
    store = _store()
except Exception as exc:
    st.error(f"Không thể kết nối cơ sở dữ liệu: {type(exc).__name__}: {exc}")
    st.stop()

try:
    runs = _df(store.recent_source_runs(30))
    signals = _df(store.recent_signals(100))
    obs = _df(store.latest_observations(500))
    bond_events = _df(store.recent_bond_events(100))
    bonds = _df(store.recent_bonds(100))
    vira_obs = _df(store.recent_observations(source="VIRA", limit=250))

    c1, c2, c3 = st.columns(3)
    if runs.empty:
        latest_status = "CH\u01afa CH\u1ea0Y"
    else:
        status_view = runs.copy()
        status_view["started_ts"] = pd.to_datetime(
            status_view["started_at"], utc=True, errors="coerce"
        )
        status_view = status_view.dropna(subset=["started_ts"]).sort_values(
            "started_ts", ascending=False
        )
    
        if status_view.empty:
            latest_status = "KH\u00d4NG X\u00c1C \u0110\u1ecaNH"
        else:
            latest_ts = status_view["started_ts"].iloc[0]
            latest_window = status_view[
                status_view["started_ts"] >= latest_ts - pd.Timedelta(minutes=15)
            ]
            statuses = latest_window["status"].astype(str).str.upper()
            failed = statuses.str.contains("FAIL|ERROR", regex=True, na=False)
            succeeded = statuses.str.contains("SUCCESS|OK", regex=True, na=False)
    
            if failed.any() and succeeded.any():
                latest_status = "DEGRADED"
            elif failed.all() and len(statuses) > 0:
                latest_status = "FAILED"
            elif succeeded.any():
                latest_status = "SUCCESS"
            else:
                latest_status = "KH\u00d4NG X\u00c1C \u0110\u1ecaNH"
    
    c1.metric("Tr\u1ea1ng th\u00e1i d\u1eef li\u1ec7u g\u1ea7n nh\u1ea5t", latest_status)
    c2.metric("Quan sát gần nhất", len(obs))
    c3.metric("Cảnh báo gần đây", len(signals))

    st.subheader("Sức khỏe hệ thống (System Health)")
    if runs.empty:
        st.info("Chưa có lịch sử chạy nguồn dữ liệu.")
    else:
        health = runs.copy()
        health["started_ts"] = pd.to_datetime(health["started_at"], utc=True, errors="coerce")
        now_utc = pd.Timestamp.now(tz="UTC")
        health["age_minutes"] = ((now_utc - health["started_ts"]).dt.total_seconds() / 60).round(1)
        health = health.sort_values("started_ts", ascending=False)
        cols = [c for c in ["source", "worker", "started_at", "age_minutes", "finished_at", "status", "records_new", "records_invalid", "error_type"] if c in health.columns]
        st.dataframe(localize_dataframe(health[cols]), width="stretch", hide_index=True)
        failures = health[health["status"].astype(str).str.contains("FAIL", case=False, na=False)]
        if not failures.empty:
            st.warning(f"Có {len(failures)} lần chạy nguồn bị lỗi gần đây. Nguồn lỗi/không lấy được dữ liệu **không đồng nghĩa** thị trường không có hoạt động.")

    st.subheader("Thị trường tiền tệ & thanh khoản — OMO NHNN")
    if obs.empty:
        st.info("Chưa có dữ liệu quan sát.")
    else:
        omo = obs[obs["metric_id"].astype(str).str.startswith("SBV.OMO")].copy()
        cols = [c for c in ["period_end", "metric_id", "entity_id", "value", "unit", "quality_flag", "fetched_at"] if c in omo.columns]
        st.dataframe(localize_dataframe(omo[cols]), width="stretch", hide_index=True)

    st.subheader("Áp lực tỷ giá (FX Pressure) — dữ liệu thị trường công khai")
    if obs.empty:
        st.info("Chưa có dữ liệu FX.")
    else:
        fx = obs[obs["metric_id"].astype(str).str.startswith("VIRA.FX.")].copy()
        if fx.empty:
            st.info("Chưa có dữ liệu FX.")
        else:
            cols = [c for c in ["period_end", "metric_id", "value", "unit", "quality_flag", "observation_method", "fetched_at"] if c in fx.columns]
            st.dataframe(localize_dataframe(fx[cols]), width="stretch", hide_index=True)
            st.caption("VIRA là nguồn thứ cấp/đối chiếu trong MVP. Cảnh báo FX là rule-based, không phải dự báo USD/VND tăng hay giảm.")

    st.subheader("Rủi ro TPCP/lãi suất — đường cong kỳ hạn suy ra từ giao dịch công khai")
    st.caption("Lợi suất kỳ hạn bên dưới được suy ra từ giao dịch outright công khai của HNX; **không phải** bộ đường cong lợi suất thương mại/chính thức của HNX.")
    if obs.empty:
        st.info("Chưa có dữ liệu HNX.")
    else:
        gov = obs[obs["metric_id"].astype(str).eq("HNX.GOV.TENOR_YIELD")].copy()
        if gov.empty:
            st.info("Chưa có quan sát lợi suất TPCP theo kỳ hạn.")
        else:
            gov["tenor"] = gov["entity_id"].astype(str).str.replace("GOV_TENOR:", "", regex=False)
            gov["tenor_years"] = pd.to_numeric(gov["tenor"].str.replace("Y", "", regex=False), errors="coerce")
            gov = gov.sort_values("tenor_years")
            c1, c2 = st.columns([2, 1])
            with c1:
                chart = gov[["tenor_years", "value"]].dropna().set_index("tenor_years")
                st.line_chart(chart, y="value", x_label="Kỳ hạn (năm)", y_label="Lợi suất (%)")
            with c2:
                cols = [c for c in ["period_end", "tenor", "value", "unit", "quality_flag", "fetched_at"] if c in gov.columns]
                st.dataframe(localize_dataframe(gov[cols]), width="stretch", hide_index=True)

        auc = obs[obs["metric_id"].astype(str).str.startswith("HNX.GOV.AUCTION")].copy()
        if not auc.empty:
            st.markdown("**Quan sát đấu thầu công khai gần nhất**")
            cols = [c for c in ["period_end", "metric_id", "entity_id", "value", "unit", "quality_flag"] if c in auc.columns]
            st.dataframe(localize_dataframe(auc[cols]), width="stretch", hide_index=True)

    st.subheader("Radar sự kiện Trái phiếu Doanh nghiệp — HNX CBIS")
    st.caption("Sự kiện được phân loại rule-based từ metadata/tiêu đề CBIS. Lifecycle event mức INFO vẫn nằm trong timeline nhưng không tự động trở thành cảnh báo rủi ro.")
    c1, c2 = st.columns([2, 1])
    with c1:
        if bond_events.empty:
            st.info("Chưa có sự kiện CBIS.")
        else:
            ev = bond_events.copy()
            cols = [c for c in ["event_date", "event_type", "bond_id", "issuer_id", "quality_flag", "source_url"] if c in ev.columns]
            st.dataframe(localize_dataframe(ev[cols]), width="stretch", hide_index=True)
    with c2:
        if bonds.empty:
            st.info("Chưa có bond master từ CBIS.")
        else:
            cols = [c for c in ["trading_code", "disclosure_code", "issuer_name", "registration_status", "first_trade_date", "last_seen_at"] if c in bonds.columns]
            st.dataframe(localize_dataframe(bonds[cols]), width="stretch", hide_index=True)

    st.subheader("Lớp ngữ nghĩa VIRA Daily / Weekly")
    st.caption("VIRA là nguồn thứ cấp/đối chiếu. FX/IBOR/TPCP tuần và OMO stock là trạng thái cuối tuần; OMO tender/win/maturity/net là flow cả tuần. Hệ thống không ép tất cả thành một dòng thứ Sáu.")
    if vira_obs.empty:
        st.info("Chưa có quan sát VIRA.")
    else:
        semantic_cols = [c for c in ["period_start", "period_end", "metric_id", "entity_id", "value", "unit", "measure_type", "frequency", "observation_method", "quality_flag", "source_published_at"] if c in vira_obs.columns]
        st.dataframe(localize_dataframe(vira_obs[semantic_cols]), width="stretch", hide_index=True)

    st.subheader("Bối cảnh vĩ mô cấu trúc — NHNN")
    st.caption("M2/tín dụng/LDR là chỉ báo bối cảnh chậm, không được dùng như cảnh báo intraday. Nếu nguồn không có timestamp công bố đáng tin cậy, hệ thống giữ riêng first_observed_at.")
    if obs.empty:
        st.info("Chưa có dữ liệu macro.")
    else:
        macro = obs[obs["metric_id"].astype(str).str.startswith("SBV.MACRO.")].copy()
        if macro.empty:
            st.info("Macro context là lớp tùy chọn và chưa được ingest.")
        else:
            cols = [c for c in ["period_end", "metric_id", "entity_id", "value", "unit", "quality_flag", "first_observed_at"] if c in macro.columns]
            st.dataframe(localize_dataframe(macro[cols]), width="stretch", hide_index=True)

    st.subheader("Cảnh báo rủi ro (Risk Signals)")
    if signals.empty:
        st.info("Chưa phát sinh cảnh báo.")
    else:
        cols = [c for c in ["generated_at", "domain", "severity", "signal_type", "entity_id", "current_value", "baseline_value", "absolute_change", "status"] if c in signals.columns]
        st.dataframe(localize_dataframe(signals[cols]), width="stretch", hide_index=True)
finally:
    store.close()
