from __future__ import annotations

import json
import os
from datetime import datetime, time
from pathlib import Path
import sys

# Make repository root importable on local Windows and Streamlit Cloud.
_REPO_ROOT = Path(__file__).resolve().parents[1] if Path(__file__).parent.name == "app" else Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.replay.point_in_time import build_snapshot
from src.storage.factory import create_store
from src.ui.display import domain_label, localize_dataframe, render_sidebar

TZ = ZoneInfo("Asia/Bangkok")
st.set_page_config(page_title="Tái dựng Lịch sử", layout="wide")
render_sidebar()
st.title("Tái dựng Lịch sử / Point-in-Time Reconstruction")
st.caption("Tái dựng những gì hệ thống có thể biết tại một timestamp lịch sử, không dùng dữ liệu tương lai.")


def load_thresholds() -> dict:
    return json.loads(Path("config/thresholds.json").read_text(encoding="utf-8"))


def frame(rows):
    return pd.DataFrame(rows) if rows else pd.DataFrame()


c1, c2, c3 = st.columns([1, 1, 1.5])
with c1:
    replay_date = st.date_input("Ngày replay")
with c2:
    replay_time = st.time_input("Giờ replay", value=time(16, 30))
with c3:
    mode_label = st.selectbox(
        "Chế độ tri thức (Knowledge mode)",
        ["SYSTEM_KNOWN", "SOURCE_AVAILABLE"],
        help="SYSTEM_KNOWN chỉ dùng dữ liệu pipeline đã fetch/quan sát trước cutoff. SOURCE_AVAILABLE tái dựng theo thời điểm nguồn đã công bố, kể cả dữ liệu được backfill vào hệ thống sau này.",
    )

cutoff_local = datetime.combine(replay_date, replay_time, tzinfo=TZ)
cutoff = cutoff_local.isoformat()
st.caption(f"Cutoff: {cutoff_local.strftime('%d/%m/%Y %H:%M:%S %z')} · Mode: {mode_label}")

if mode_label == "SOURCE_AVAILABLE":
    st.warning("SOURCE_AVAILABLE là chế độ nghiên cứu lịch sử. Một bản ghi có thể xuất hiện dù crawler của project chỉ ingest nó sau đó. Dùng SYSTEM_KNOWN nếu cần replay nghiêm ngặt chống hindsight.")

try:
    store = create_store(local_db_path=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    snapshot = build_snapshot(store, cutoff, load_thresholds(), mode=mode_label)
finally:
    if "store" in locals():
        store.close()

states = snapshot.domain_state
cols = st.columns(4)
for idx, domain in enumerate(["LIQUIDITY", "FX", "RATES", "CORPORATE_BOND"]):
    cols[idx].metric(domain_label(domain), states.get(domain, "NORMAL"))

st.subheader("Snapshot tại thời điểm lịch sử")
obs = frame(snapshot.observations)
if obs.empty:
    st.info("Không có observation đủ điều kiện tại cutoff này.")
else:
    wanted = [c for c in ["period_end", "source", "metric_id", "entity_id", "value", "unit", "measure_type", "observation_method", "quality_flag", "source_published_at", "first_observed_at"] if c in obs.columns]
    st.dataframe(localize_dataframe(obs[wanted]), width="stretch", hide_index=True)

st.subheader("Deterministic signal tái dựng tại cutoff")
sig = frame(snapshot.reconstructed_signals)
if sig.empty:
    st.info("Với dữ liệu đủ điều kiện tại cutoff này, không có deterministic signal nào được kích hoạt.")
else:
    wanted = [c for c in ["domain", "severity", "signal_type", "entity_id", "current_value", "baseline_value", "absolute_change"] if c in sig.columns]
    st.dataframe(localize_dataframe(sig[wanted]), width="stretch", hide_index=True)

with st.expander("Signal thực sự đã được hệ thống ghi nhận"):
    recorded = frame(snapshot.recorded_signals)
    if recorded.empty:
        st.info("Chưa có signal nào được ghi nhận trước cutoff này.")
    else:
        st.dataframe(localize_dataframe(recorded), width="stretch", hide_index=True)

st.subheader("Sự kiện TPDN đã biết tại cutoff")
ev = frame(snapshot.events)
if ev.empty:
    st.info("Không có sự kiện TPDN đủ điều kiện tại cutoff này.")
else:
    wanted = [c for c in ["announced_at", "first_observed_at", "event_type", "bond_id", "issuer_id", "quality_flag", "source_url"] if c in ev.columns]
    st.dataframe(localize_dataframe(ev[wanted]), width="stretch", hide_index=True)

st.subheader("Timeline replay")
tl = frame(snapshot.timeline)
if tl.empty:
    st.info("Không có mục timeline.")
else:
    wanted = [c for c in ["timestamp", "kind", "domain", "severity", "label", "value", "source", "quality_flag"] if c in tl.columns]
    st.dataframe(localize_dataframe(tl[wanted]), width="stretch", hide_index=True)

with st.expander("Source run đã tồn tại trước cutoff"):
    runs = frame(snapshot.source_runs)
    if runs.empty:
        st.info("Chưa có source-run history trước cutoff này.")
    else:
        wanted = [c for c in ["started_at", "source", "worker", "status", "records_new", "records_invalid", "error_type"] if c in runs.columns]
        st.dataframe(localize_dataframe(runs[wanted]), width="stretch", hide_index=True)

st.caption("Replay signal được tính lại bằng deterministic rules chỉ từ observation/event đủ điều kiện theo mode đã chọn. Đây là analytical reconstruction; chỉ signal xuất hiện trong mục Recorded signals mới chứng minh hệ thống từng ghi cảnh báo đó trong lịch sử.")
