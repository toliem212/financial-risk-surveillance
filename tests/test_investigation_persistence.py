from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.investigation.case_management import case_workflow
from src.investigation.persistence import (
    audit_rows,
    available_statuses,
    open_case,
    update_case,
)
from src.storage.sqlite_store import SQLiteStore
from src.version import SCHEMA_VERSION


def _signal(signal_id: str = "signal-1") -> dict:
    return {
        "signal_id": signal_id,
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
        "evidence_json": {"current_period": "2026-09-30", "unit": "bp"},
        "status": "OPEN",
    }


def _store(tmp_path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "db.sqlite")
    store.insert_signals([_signal()])
    return store


def test_schema_v2_adds_investigation_tables(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    try:
        counts = store.counts()
        assert "investigation_case" in counts
        assert "investigation_audit" in counts
        assert SCHEMA_VERSION == "2"
    finally:
        store.close()


def test_open_case_persists_case_and_open_audit(tmp_path):
    store = _store(tmp_path)
    try:
        case = open_case(
            store,
            signal_id="signal-1",
            priority="CAO",
            owner="Market Risk",
            note="Rà soát curve và PV01.",
        )
        assert case["status"] == "OPEN"
        assert case["priority"] == "CAO"
        assert case["owner"] == "Market Risk"
        assert store.get_investigation_case_by_signal("signal-1")["case_id"] == case["case_id"]
        audit = audit_rows(store, case["case_id"])
        assert len(audit) == 1
        assert audit[0]["action_type"] == "CASE_OPENED"
        assert audit[0]["to_status"] == "OPEN"
    finally:
        store.close()


def test_open_case_is_idempotent_per_signal(tmp_path):
    store = _store(tmp_path)
    try:
        first = open_case(store, signal_id="signal-1", priority="CAO")
        second = open_case(store, signal_id="signal-1", priority="KHẨN")
        assert second["case_id"] == first["case_id"]
        assert len(audit_rows(store, first["case_id"])) == 1
    finally:
        store.close()


def test_invalid_case_transition_is_blocked(tmp_path):
    store = _store(tmp_path)
    try:
        case = open_case(store, signal_id="signal-1", priority="CAO")
        with pytest.raises(ValueError, match="Invalid case transition"):
            update_case(store, case_id=case["case_id"], status="CLOSED", note="close", resolution="done")
    finally:
        store.close()


def test_resolution_required_before_resolved(tmp_path):
    store = _store(tmp_path)
    try:
        case = open_case(store, signal_id="signal-1", priority="CAO")
        case = update_case(store, case_id=case["case_id"], status="INVESTIGATING", owner="Risk")
        with pytest.raises(ValueError, match="kết quả xử lý"):
            update_case(store, case_id=case["case_id"], status="RESOLVED", note="Đã rà soát")
    finally:
        store.close()


def test_case_lifecycle_and_audit_trail_are_persisted(tmp_path):
    store = _store(tmp_path)
    try:
        case = open_case(store, signal_id="signal-1", priority="CAO", owner="Risk")
        case = update_case(store, case_id=case["case_id"], status="INVESTIGATING", owner="Risk")
        case = update_case(
            store,
            case_id=case["case_id"],
            status="ESCALATED",
            owner="Risk",
            note="PV01 gần ngưỡng; chuyển cấp rà soát.",
        )
        case = update_case(
            store,
            case_id=case["case_id"],
            status="RESOLVED",
            owner="Risk",
            note="Đã xác minh dữ liệu và exposure.",
            resolution="Không có breach; tiếp tục monitoring.",
        )
        case = update_case(
            store,
            case_id=case["case_id"],
            status="CLOSED",
            owner="Risk",
            note="Đóng case sau follow-up.",
            resolution=case["resolution"],
        )
        assert case["status"] == "CLOSED"
        assert case["closed_at"] is not None
        audit = audit_rows(store, case["case_id"])
        assert len(audit) == 5
        assert audit[0]["to_status"] == "CLOSED"
        assert {row["action_type"] for row in audit} == {"CASE_OPENED", "STATUS_CHANGED"}
    finally:
        store.close()


def test_workflow_uses_persisted_case_status_when_available():
    case = SimpleNamespace(
        signal={"severity": "HIGH", "domain": "RATES", "status": "OPEN"},
        data_quality={"status": "OK", "note": "DQ ok"},
        related_observations=[{"metric_id": "HNX.GOV.TENOR_YIELD"}],
        historical_context={"count": 10},
    )
    out = case_workflow(case, {"status": "ESCALATED"})
    assert out[-1]["state"] == "ĐÃ ESCALATE"
    assert "lưu và theo dõi" in out[-1]["detail"]
    assert available_statuses("ESCALATED") == ["ESCALATED", "INVESTIGATING", "RESOLVED"]


def test_risk_feed_ui_surfaces_persistent_case_controls():
    from pathlib import Path

    text = Path("app/pages/1_Risk_Feed.py").read_text(encoding="utf-8")
    assert "Case đang xử lý" in text
    assert "Case status" in text
    assert "Quản lý case & Audit Trail" in text
    assert "Mở investigation case" in text
    assert "Lưu cập nhật case" in text
