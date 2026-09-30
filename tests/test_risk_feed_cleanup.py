from __future__ import annotations

import json

from src.investigation.risk_feed import build_investigation_case, build_risk_feed
from src.storage.sqlite_store import SQLiteStore


def _obs(oid, entity, value, period, *, metric="HNX.GOV.TENOR_YIELD", source="HNX"):
    return {
        "observation_id": oid,
        "metric_id": metric,
        "entity_type": "GOV_TENOR",
        "entity_id": entity,
        "value": value,
        "unit": "pct",
        "period_start": period,
        "period_end": period,
        "as_of_time": None,
        "measure_type": "SNAPSHOT",
        "frequency": "DAILY",
        "source": source,
        "source_url": "fixture://cleanup",
        "source_published_at": f"{period}T01:00:00+00:00",
        "first_observed_at": f"{period}T02:00:00+00:00",
        "fetched_at": f"{period}T02:00:00+00:00",
        "processed_at": f"{period}T02:00:00+00:00",
        "observation_method": "DIRECT_DAILY",
        "quality_flag": "A",
        "raw_object_id": "raw/test",
        "parser_version": "test",
        "record_hash": oid,
        "dims_json": json.dumps({}),
    }


def _curve_signal():
    return {
        "signal_id": "curve-1",
        "signal_type": "CURVE_STEEPENING",
        "domain": "RATES",
        "entity_type": "GOV_CURVE",
        "entity_id": "GOV_CURVE:5Y10Y",
        "generated_at": "2026-09-30T01:00:00+00:00",
        "current_value": 60.0,
        "baseline_value": 50.0,
        "absolute_change": 10.0,
        "relative_change": None,
        "z_score": None,
        "percentile": None,
        "threshold": 5.0,
        "severity": "HIGH",
        "evidence_json": {
            "current_period": "2026-09-30",
            "unit": "bp",
        },
        "status": "OPEN",
    }


def test_curve_history_is_derived_in_bp_not_mixed_raw_tenor_levels(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        _obs("5a", "GOV_TENOR:5Y", 3.0, "2026-09-29"),
        _obs("10a", "GOV_TENOR:10Y", 3.5, "2026-09-29"),
        _obs("5b", "GOV_TENOR:5Y", 3.1, "2026-09-30"),
        _obs("10b", "GOV_TENOR:10Y", 3.7, "2026-09-30"),
    ])
    store.insert_signals([_curve_signal()])
    case = build_investigation_case(store, "curve-1")
    assert case.historical_context["unit"] == "bp"
    assert case.historical_context["count"] == 2
    assert round(case.historical_context["first"], 6) == 50.0
    assert round(case.historical_context["latest"], 6) == 60.0
    store.close()


def test_rates_related_context_prioritizes_hnx_before_omo(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_observations([
        _obs("5b", "GOV_TENOR:5Y", 3.1, "2026-09-30"),
        _obs("10b", "GOV_TENOR:10Y", 3.7, "2026-09-30"),
        _obs("omo", "SBV_OMO:INJECTION:7D", 4.5, "2026-09-30", metric="SBV.OMO.RATE", source="SBV"),
    ])
    store.insert_signals([_curve_signal()])
    case = build_investigation_case(store, "curve-1")
    assert case.related_observations[0]["metric_id"].startswith("HNX.GOV")
    assert "public observations" not in case.data_quality["note"]
    store.close()


def test_feed_uses_market_date_instead_of_ingestion_timestamp(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    row = _curve_signal()
    row["generated_at"] = "2026-10-01T08:00:00+00:00"
    row["evidence_json"] = {"current_period": "2026-09-29", "unit": "bp"}
    store.insert_signals([row])
    feed = build_risk_feed(store)
    signal = next(x for x in feed if x["item_type"] == "SIGNAL")
    assert signal["timestamp"] == "2026-09-29"
    assert signal["generated_at"].startswith("2026-10-01")
    store.close()


def test_bond_event_feed_uses_observed_date_and_keeps_future_event_date_separate(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_bond_events([
        {
            "event_id": "event-1",
            "issuer_id": "issuer-1",
            "bond_id": "bond-1",
            "event_type": "DELISTING",
            "event_date": "2026-10-21",
            "effective_date": None,
            "announced_at": "2026-09-29T08:00:00+00:00",
            "first_observed_at": "2026-09-29T09:00:00+00:00",
            "source": "HNX_CBIS",
            "source_url": "fixture://cbis",
            "event_payload": {},
            "quality_flag": "A",
            "event_hash": "event-hash-1",
        }
    ])
    feed = build_risk_feed(store, signal_limit=10, event_limit=10, limit=20)
    event = next(x for x in feed if x["item_type"] == "EVENT")
    assert event["timestamp"] == "2026-09-29"
    assert event["event_date"] == "2026-10-21"
    assert event["status"] is None
    store.close()


def test_signal_feed_has_no_event_date(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_signals([_curve_signal()])
    feed = build_risk_feed(store, signal_limit=10, event_limit=10, limit=20)
    signal = next(x for x in feed if x["item_type"] == "SIGNAL")
    assert signal["event_date"] is None
    store.close()
