from __future__ import annotations

from pathlib import Path

from src.investigation.persistence import open_case, update_case
from src.reporting.daily_brief import build_daily_risk_brief
from src.storage.sqlite_store import SQLiteStore


def _signal() -> dict:
    return {
        "signal_id": "signal-mgmt-1",
        "signal_type": "CURVE_FLATTENING",
        "domain": "RATES",
        "entity_type": "GOV_CURVE",
        "entity_id": "GOV_CURVE:5Y10Y",
        "generated_at": "2026-09-30T01:00:00+00:00",
        "current_value": -46.8,
        "baseline_value": -35.0,
        "absolute_change": -11.8,
        "relative_change": None,
        "z_score": None,
        "percentile": None,
        "threshold": 5.0,
        "severity": "HIGH",
        "evidence_json": {"unit": "bp"},
        "status": "OPEN",
    }


def test_daily_brief_surfaces_active_investigation_case(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    try:
        store.insert_signals([_signal()])
        case = open_case(
            store,
            signal_id="signal-mgmt-1",
            priority="CAO",
            owner="Market Risk",
        )
        update_case(
            store,
            case_id=case["case_id"],
            status="INVESTIGATING",
            owner="Market Risk",
        )
        brief = build_daily_risk_brief(store)
        assert "Investigation & escalation" in brief
        assert "1 case đang xử lý" in brief
        assert "Market Risk" in brief
        assert "GOV_CURVE:5Y10Y" in brief
    finally:
        store.close()


def test_home_surfaces_active_case_control_room():
    text = Path("app/Home.py").read_text(encoding="utf-8")
    assert "Case đang xử lý" in text
    assert "Investigation & escalation" in text
    assert "recent_investigation_cases" in text


def test_risk_feed_uses_business_evidence_view_and_localized_case_section():
    text = Path("app/pages/1_Risk_Feed.py").read_text(encoding="utf-8")
    assert "Bằng chứng chính" in text
    assert "Chi tiết kỹ thuật của signal" in text
    assert "Quản lý case & Audit Trail" in text
    assert "MỞ CASE" in text
    assert "ĐỔI TRẠNG THÁI" in text
