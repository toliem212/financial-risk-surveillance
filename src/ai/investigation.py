from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.ai.client import AIResult, AIService
from src.ai.schemas import INVESTIGATION_SCHEMA

PROMPT_VERSION = "risk-investigation-v1"

INSTRUCTIONS = """You are an AI enrichment layer inside a financial-risk surveillance prototype.
Use ONLY the supplied deterministic evidence. Write concise Vietnamese.
Do not invent missing market data, causes, bank positions, limits, P&L, or exposures.
Do not treat co-movement as proven causality. Phrase transmission as possible channels.
Do not give trading, investment, or hedge recommendations.
If data quality is weak, make that limitation prominent.
Return only the required structured fields."""


def compact_case(case, *, max_related: int = 12) -> dict[str, Any]:
    signal = dict(case.signal)
    keep_signal = {
        k: signal.get(k) for k in [
            "signal_type", "domain", "entity_type", "entity_id", "generated_at", "severity",
            "current_value", "baseline_value", "absolute_change", "relative_change", "threshold",
        ] if signal.get(k) is not None
    }
    related = []
    for r in case.related_observations[:max_related]:
        related.append({k: r.get(k) for k in [
            "period_end", "metric_id", "entity_id", "value", "unit", "source",
            "quality_flag", "observation_method",
        ] if r.get(k) is not None})
    return {
        "signal": keep_signal,
        "evidence": case.evidence,
        "data_quality": case.data_quality,
        "historical_context": case.historical_context,
        "related_observations": related,
        "deterministic_transmission_context": case.possible_risk_transmission[:3],
        "deterministic_monitor_next": case.monitor_next[:3],
    }


def generate_ai_investigation(service: AIService, case) -> AIResult:
    payload = compact_case(case)
    return service.run_structured(
        feature="risk_investigation",
        payload=payload,
        instructions=INSTRUCTIONS,
        schema_name="risk_investigation",
        schema=INVESTIGATION_SCHEMA,
        prompt_version=PROMPT_VERSION,
        max_output_tokens=service.policy.investigation_max_output_tokens,
    )
