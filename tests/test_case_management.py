from __future__ import annotations

from types import SimpleNamespace

from src.investigation.case_management import (
    case_priority,
    case_workflow,
    evidence_summary,
    escalation_guidance,
    feed_summary,
    latest_feed_view,
    next_actions,
    signal_value_table,
)


def _case(
    severity="HIGH",
    domain="RATES",
    dq="OK",
    status="OPEN",
):
    return SimpleNamespace(
        signal={
            "severity": severity,
            "domain": domain,
            "status": status,
        },
        data_quality={
            "status": dq,
            "note": "DQ note",
        },
        related_observations=[
            {"metric_id": "HNX.GOV.TENOR_YIELD"},
        ],
        historical_context={"count": 10},
    )


def test_feed_summary_counts_signals_and_events():
    feed = [
        {
            "item_type": "SIGNAL",
            "severity": "HIGH",
            "domain": "RATES",
            "status": "OPEN",
        },
        {
            "item_type": "SIGNAL",
            "severity": "MEDIUM",
            "domain": "FX",
            "status": "CLOSED",
        },
        {
            "item_type": "EVENT",
            "severity": "INFO",
            "domain": "CORPORATE_BOND",
        },
    ]
    out = feed_summary(feed)
    assert out["signals"] == 2
    assert out["events"] == 1
    assert out["high_critical"] == 1
    assert out["open_signals"] == 1
    assert out["domains"] == 2


def test_high_clean_case_has_high_priority():
    out = case_priority(_case(severity="HIGH", dq="OK"))
    assert out["priority"] == "CAO"


def test_dq_review_overrides_economic_escalation_priority():
    out = case_priority(
        _case(severity="CRITICAL", dq="REVIEW")
    )
    assert out["priority"] == "XÁC MINH DỮ LIỆU"
    assert "dữ liệu" in out["rationale"].lower()


def test_rates_case_has_portfolio_action_and_escalation():
    case = _case(
        severity="HIGH",
        domain="RATES",
        dq="OK",
    )
    actions = " ".join(next_actions(case))
    assert "PV01" in actions
    assert "escalation" in actions.lower()
    assert "Review trong ngày" in escalation_guidance(case)


def test_workflow_uses_persisted_signal_status_without_inventing_case_state():
    out = case_workflow(
        _case(
            severity="MEDIUM",
            domain="FX",
            dq="CAUTION",
            status="OPEN",
        )
    )
    assert out[-1]["state"] == "CHƯA MỞ CASE"
    assert "chưa được đưa vào luồng xử lý case" in out[-1]["detail"]


def test_latest_feed_view_collapses_historical_repeats():
    feed = [
        {
            "item_type": "SIGNAL",
            "signal_type": "YIELD_MOVE_HIGH",
            "entity_id": "GOV_TENOR:10Y",
            "timestamp": "2026-09-29",
            "generated_at": "2026-09-29T13:00:00+00:00",
            "severity": "HIGH",
            "domain": "RATES",
            "feed_id": "old",
        },
        {
            "item_type": "SIGNAL",
            "signal_type": "YIELD_MOVE_HIGH",
            "entity_id": "GOV_TENOR:10Y",
            "timestamp": "2026-09-30",
            "generated_at": "2026-09-30T01:00:00+00:00",
            "severity": "MEDIUM",
            "domain": "RATES",
            "feed_id": "new",
        },
    ]
    out = latest_feed_view(feed)
    assert len(out) == 1
    assert out[0]["feed_id"] == "new"


def test_curve_signal_value_table_uses_basis_points():
    case = _case()
    case.signal.update({
        "signal_type": "CURVE_STEEPENING",
        "current_value": 57.8456,
        "baseline_value": 49.649,
        "absolute_change": 8.1966,
        "threshold": 5.0,
    })
    out = signal_value_table(case)
    assert set(out["Đơn vị"]) == {"bp"}


def test_evidence_summary_localizes_common_fields():
    case = _case()
    case.evidence = {
        "unit": "bp",
        "curve_type": "derived_public_trade_curve",
        "current_period": "2026-09-29",
        "nested": {"skip": True},
    }
    out = evidence_summary(case)
    assert list(out["Bằng chứng"]) == ["Đơn vị", "Loại đường cong", "Ngày dữ liệu"]
    assert "nested" not in out["Bằng chứng"].astype(str).str.lower().tolist()
