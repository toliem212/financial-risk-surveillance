from __future__ import annotations

import json
from pathlib import Path

from src.replay.point_in_time import build_snapshot
from src.storage.sqlite_store import SQLiteStore


def obs(*, oid, metric, entity, value, period, first_seen, published=None, source="SBV"):
    return {
        "observation_id": oid,
        "metric_id": metric,
        "entity_type": "OMO_TERM" if metric.startswith("SBV.OMO") else "GOV_TENOR",
        "entity_id": entity,
        "value": value,
        "unit": "pct",
        "period_start": period,
        "period_end": period,
        "as_of_time": None,
        "measure_type": "SNAPSHOT",
        "frequency": "DAILY",
        "source": source,
        "source_url": "fixture://replay",
        "source_published_at": published,
        "first_observed_at": first_seen,
        "fetched_at": first_seen,
        "processed_at": first_seen,
        "observation_method": "DIRECT_SOURCE",
        "quality_flag": "A",
        "raw_object_id": "raw/test",
        "parser_version": "test",
        "record_hash": oid,
        "dims_json": json.dumps({}),
    }


def thresholds():
    return json.loads(Path("config/thresholds.json").read_text(encoding="utf-8"))


def test_system_known_excludes_future_ingestion(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        obs(oid="a", metric="SBV.OMO.RATE", entity="OMO:7D", value=4.0, period="2026-09-28", first_seen="2026-09-28T10:00:00+00:00", published="2026-09-28T09:55:00+00:00"),
        obs(oid="b", metric="SBV.OMO.RATE", entity="OMO:7D", value=5.0, period="2026-09-29", first_seen="2026-09-29T11:00:00+00:00", published="2026-09-29T09:00:00+00:00"),
    ])
    snap = build_snapshot(store, "2026-09-29T10:00:00+00:00", thresholds(), mode="SYSTEM_KNOWN")
    assert len(snap.observations) == 1
    assert snap.observations[0]["value"] == 4.0
    store.close()


def test_source_available_can_include_later_backfill(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        obs(oid="a", metric="SBV.OMO.RATE", entity="OMO:7D", value=4.0, period="2026-09-28", first_seen="2026-09-28T10:00:00+00:00", published="2026-09-28T09:55:00+00:00"),
        obs(oid="b", metric="SBV.OMO.RATE", entity="OMO:7D", value=5.0, period="2026-09-29", first_seen="2026-09-30T11:00:00+00:00", published="2026-09-29T09:00:00+00:00"),
    ])
    strict = build_snapshot(store, "2026-09-29T10:00:00+00:00", thresholds(), mode="SYSTEM_KNOWN")
    source = build_snapshot(store, "2026-09-29T10:00:00+00:00", thresholds(), mode="SOURCE_AVAILABLE")
    assert strict.observations[0]["value"] == 4.0
    assert source.observations[0]["value"] == 5.0
    store.close()


def test_replay_reconstructs_omo_signal_without_future_data(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        obs(oid="a", metric="SBV.OMO.RATE", entity="OMO:7D", value=4.0, period="2026-09-28", first_seen="2026-09-28T10:00:00+00:00"),
        obs(oid="b", metric="SBV.OMO.RATE", entity="OMO:7D", value=4.6, period="2026-09-29", first_seen="2026-09-29T09:30:00+00:00"),
        obs(oid="c", metric="SBV.OMO.RATE", entity="OMO:7D", value=7.0, period="2026-09-30", first_seen="2026-09-30T09:30:00+00:00"),
    ])
    snap = build_snapshot(store, "2026-09-29T10:00:00+00:00", thresholds(), mode="SYSTEM_KNOWN")
    alerts = [s for s in snap.reconstructed_signals if s["signal_type"] == "OMO_RATE_CHANGE_HIGH"]
    assert len(alerts) == 1
    assert round(alerts[0]["absolute_change"], 6) == 60.0
    assert alerts[0]["severity"] == "HIGH"
    assert snap.domain_state["LIQUIDITY"] == "HIGH"
    store.close()


def test_future_bond_event_is_not_visible(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    event = {
        "event_id": "e1", "issuer_id": None, "bond_id": "BOND1", "event_type": "PAYMENT_DELAY",
        "event_date": "2026-09-29", "effective_date": None, "announced_at": "2026-09-29T12:00:00+00:00",
        "first_observed_at": "2026-09-29T12:05:00+00:00", "source": "HNX_CBIS", "source_url": "fixture://event",
        "event_payload": {"title": "delay"}, "quality_flag": "A", "event_hash": "eh1",
    }
    store.insert_bond_events([event])
    before = build_snapshot(store, "2026-09-29T11:00:00+00:00", thresholds())
    after = build_snapshot(store, "2026-09-29T13:00:00+00:00", thresholds())
    assert before.events == []
    assert len(after.events) == 1
    assert any(s["signal_type"] == "CB_PAYMENT_DELAY" for s in after.reconstructed_signals)
    store.close()


def test_replay_handles_json_event_payload_from_sqlite(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    event = {
        "event_id": "e2", "issuer_id": None, "bond_id": "BOND2", "event_type": "TRADING_SUSPENSION",
        "event_date": "2026-09-29", "effective_date": None, "announced_at": "2026-09-29T08:00:00+00:00",
        "first_observed_at": "2026-09-29T08:05:00+00:00", "source": "HNX_CBIS", "source_url": "fixture://event2",
        "event_payload": {"reason": "Mua lại"}, "quality_flag": "A", "event_hash": "eh2",
    }
    store.insert_bond_events([event])
    snap = build_snapshot(store, "2026-09-29T09:00:00+00:00", thresholds())
    assert len(snap.events) == 1
    assert not any(s["signal_type"] == "CB_TRADING_SUSPENSION" for s in snap.reconstructed_signals)
    store.close()
