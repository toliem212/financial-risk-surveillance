from __future__ import annotations

import json
from pathlib import Path

from src.investigation.risk_feed import build_investigation_case, build_risk_feed
from src.replay.point_in_time import build_snapshot
from src.signals.fx import build_fx_signals
from src.storage.sqlite_store import SQLiteStore


def thresholds():
    return json.loads(Path("config/thresholds.json").read_text(encoding="utf-8"))


def obs(*, oid, metric, entity, value, period, quality="C", source="VIRA"):
    return {
        "observation_id": oid,
        "metric_id": metric,
        "entity_type": "FX_MARKET" if metric.startswith("VIRA.FX") else "GOV_TENOR",
        "entity_id": entity,
        "value": value,
        "unit": "VND_per_USD" if metric.startswith("VIRA.FX") else "pct",
        "period_start": period,
        "period_end": period,
        "as_of_time": None,
        "measure_type": "SNAPSHOT",
        "frequency": "DAILY",
        "source": source,
        "source_url": "fixture://m7",
        "source_published_at": f"{period}T01:00:00+00:00",
        "first_observed_at": f"{period}T02:00:00+00:00",
        "fetched_at": f"{period}T02:00:00+00:00",
        "processed_at": f"{period}T02:00:00+00:00",
        "observation_method": "DIRECT_DAILY",
        "quality_flag": quality,
        "raw_object_id": "raw/test",
        "parser_version": "test",
        "record_hash": oid,
        "dims_json": json.dumps({}),
    }


def signal_row(signal_id="s1", *, domain="FX", signal_type="FX_MOVE_HIGH", severity="HIGH"):
    return {
        "signal_id": signal_id,
        "signal_type": signal_type,
        "domain": domain,
        "entity_type": "FX_MARKET",
        "entity_id": "INTERBANK",
        "generated_at": "2026-09-29T03:00:00+00:00",
        "current_value": 26200.0,
        "baseline_value": 26000.0,
        "absolute_change": 200.0,
        "relative_change": 0.7692307,
        "z_score": None,
        "percentile": None,
        "threshold": 0.3,
        "severity": severity,
        "evidence_json": {"metric": "VIRA.FX.INTERBANK", "current_period": "2026-09-29", "source": "VIRA"},
        "status": "OPEN",
    }


def test_fx_move_and_policy_reference_signals(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    previous = obs(oid="p", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26000, period="2026-09-28")
    current = obs(oid="c", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26200, period="2026-09-29")
    sell = obs(oid="r", metric="VIRA.FX.SBV_SELL", entity="SBV_SELL", value=26300, period="2026-09-29")
    store.insert_observations([previous, current, sell])
    signals = build_fx_signals([current, sell], store, thresholds())
    types = {s["signal_type"]: s for s in signals}
    assert types["FX_MOVE_HIGH"]["severity"] == "HIGH"
    assert types["FX_POLICY_REFERENCE_PROXIMITY"]["severity"] == "HIGH"
    assert "ceiling" not in types["FX_POLICY_REFERENCE_PROXIMITY"]["evidence_json"]["reference_label"].lower()
    store.close()


def test_risk_feed_keeps_info_lifecycle_event_without_alert_duplication(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_signals([signal_row()])
    store.insert_bond_events([{
        "event_id": "e1", "issuer_id": "I1", "bond_id": "B1", "event_type": "BUYBACK",
        "event_date": "2026-09-29", "effective_date": None, "announced_at": "2026-09-29T02:00:00+00:00",
        "first_observed_at": "2026-09-29T02:05:00+00:00", "source": "HNX_CBIS", "source_url": "fixture://e1",
        "event_payload": {"reason": "Mua lại"}, "quality_flag": "A", "event_hash": "eh1",
    }])
    feed = build_risk_feed(store)
    assert any(x["item_type"] == "SIGNAL" and x["signal_id"] == "s1" for x in feed)
    assert any(x["item_type"] == "EVENT" and x["event_id"] == "e1" and x["severity"] == "INFO" for x in feed)
    store.close()


def test_investigation_case_builds_context_and_dq_state(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    rows = [
        obs(oid="p", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26000, period="2026-09-28", quality="C"),
        obs(oid="c", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26200, period="2026-09-29", quality="D"),
        obs(oid="g", metric="HNX.GOV.TENOR_YIELD", entity="GOV_TENOR:10Y", value=4.50, period="2026-09-29", quality="B", source="HNX"),
    ]
    store.insert_observations(rows)
    store.insert_signals([signal_row()])
    case = build_investigation_case(store, "s1")
    assert case.data_quality["status"] == "REVIEW"
    assert case.historical_context["count"] == 2
    assert any(r["metric_id"] == "HNX.GOV.TENOR_YIELD" for r in case.related_observations)
    assert case.possible_risk_transmission
    assert case.monitor_next
    store.close()


def test_replay_reconstructs_fx_signal(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        obs(oid="p", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26000, period="2026-09-28"),
        obs(oid="c", metric="VIRA.FX.INTERBANK", entity="INTERBANK", value=26200, period="2026-09-29"),
        obs(oid="r", metric="VIRA.FX.SBV_SELL", entity="SBV_SELL", value=26300, period="2026-09-29"),
    ])
    snap = build_snapshot(store, "2026-09-29T04:00:00+00:00", thresholds())
    types = {s["signal_type"] for s in snap.reconstructed_signals}
    assert "FX_MOVE_HIGH" in types
    assert "FX_POLICY_REFERENCE_PROXIMITY" in types
    assert snap.domain_state["FX"] == "HIGH"
    store.close()
