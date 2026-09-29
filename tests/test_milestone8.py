from __future__ import annotations

from dataclasses import replace

import pytest

from src.ai.client import AIBudgetExceeded, AIDisabled, AIService, TransportResult
from src.ai.disclosure import classify_disclosure
from src.ai.investigation import compact_case, generate_ai_investigation
from src.ai.policy import AIPolicy
from src.investigation.risk_feed import InvestigationCase
from src.storage.sqlite_store import SQLiteStore


class FakeTransport:
    def __init__(self, data: dict):
        self.data = data
        self.calls = 0
        self.last_input = None

    def create_structured(self, **kwargs):
        self.calls += 1
        self.last_input = kwargs
        return TransportResult(
            data=self.data, response_id=f"resp-{self.calls}", input_tokens=120,
            cached_input_tokens=20, output_tokens=40, total_tokens=160,
        )


def policy(**kwargs):
    base = AIPolicy(
        enabled=True, model="gpt-5.6-luna", daily_call_limit=20, max_input_chars=12000,
        investigation_max_output_tokens=450, disclosure_max_output_tokens=220,
        reasoning_effort="none", input_usd_per_mtok=1.0,
        cached_input_usd_per_mtok=0.1, output_usd_per_mtok=2.0,
    )
    return replace(base, **kwargs)


def investigation_data():
    return {
        "summary": "Tóm tắt ngắn.", "what_changed": "O/N tăng.",
        "why_it_matters": "Điều kiện thanh khoản có thể chặt hơn.",
        "data_quality_note": "Nguồn đã được kiểm tra.",
        "possible_transmission": ["Có thể truyền sang short-end rates."],
        "monitor_next": ["Theo dõi OMO tiếp theo."],
        "caveats": ["Không suy ra exposure của ngân hàng."],
    }


def disclosure_data():
    return {
        "event_type": "MATURITY_EXTENSION", "confidence": "HIGH",
        "reason": "Tiêu đề nêu gia hạn kỳ hạn.", "bond_codes": ["ABC123"],
        "effective_date": "", "material_terms_changed": True,
        "requires_human_review": False,
    }


def test_ai_disabled_never_calls_transport(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    fake = FakeTransport(investigation_data())
    svc = AIService(store, policy=policy(enabled=False), transport=fake)
    with pytest.raises(AIDisabled):
        svc.run_structured(feature="x", payload={"a": 1}, instructions="x", schema_name="x", schema={"type":"object"}, prompt_version="v1", max_output_tokens=100)
    assert fake.calls == 0
    store.close()


def test_ai_cache_prevents_second_paid_call_and_logs_usage(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    fake = FakeTransport(disclosure_data())
    svc = AIService(store, policy=policy(), transport=fake)
    a = classify_disclosure(svc, title="Gia hạn kỳ hạn trái phiếu ABC123")
    b = classify_disclosure(svc, title="Gia hạn kỳ hạn trái phiếu ABC123")
    assert fake.calls == 1
    assert a.cached is False
    assert b.cached is True
    usage = store.ai_usage_summary("2000-01-01T00:00:00+00:00")
    assert usage["api_calls"] == 1
    assert usage["cache_hits"] == 1
    assert usage["total_tokens"] == 160
    assert float(usage["estimated_cost_usd"]) > 0
    store.close()


def test_daily_call_limit_blocks_new_payload(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    fake = FakeTransport(disclosure_data())
    svc = AIService(store, policy=policy(daily_call_limit=1), transport=fake)
    classify_disclosure(svc, title="Gia hạn trái phiếu ABC123")
    with pytest.raises(AIBudgetExceeded):
        classify_disclosure(svc, title="Thay đổi tài sản bảo đảm XYZ456")
    assert fake.calls == 1
    store.close()


def test_investigation_context_is_compact_and_ai_uses_deterministic_case(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    case = InvestigationCase(
        signal={"signal_type":"FX_MOVE_HIGH","domain":"FX","entity_id":"INTERBANK","severity":"HIGH","current_value":26200,"baseline_value":26000,"absolute_change":200,"relative_change":0.77,"generated_at":"2026-09-29T03:00:00+00:00"},
        evidence={"metric":"VIRA.FX.INTERBANK","source":"VIRA"},
        related_observations=[{"metric_id":"VIRA.FX.INTERBANK","entity_id":"INTERBANK","value":26200,"unit":"VND_per_USD","source":"VIRA","quality_flag":"B","observation_method":"DIRECT_DAILY","period_end":"2026-09-29"}] * 30,
        historical_context={"count":20,"min":25000,"max":26200},
        data_quality={"status":"OK","flags_present":["B"]},
        possible_risk_transmission=["Possible channel 1", "Possible channel 2"],
        monitor_next=["Monitor FX", "Monitor liquidity"],
    )
    payload = compact_case(case)
    assert len(payload["related_observations"]) == 12
    fake = FakeTransport(investigation_data())
    result = generate_ai_investigation(AIService(store, policy=policy(), transport=fake), case)
    assert result.data["caveats"]
    assert fake.last_input["max_output_tokens"] == 450
    assert fake.last_input["reasoning_effort"] == "none"
    store.close()


def test_ai_cost_rates_are_configurable_not_hardcoded():
    p = policy(input_usd_per_mtok=0, cached_input_usd_per_mtok=0, output_usd_per_mtok=0)
    assert p.estimate_cost_usd(input_tokens=1000, cached_input_tokens=0, output_tokens=100) is None
