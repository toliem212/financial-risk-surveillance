from __future__ import annotations

from src.ai.client import AIResult, AIService
from src.ai.schemas import DISCLOSURE_SCHEMA

PROMPT_VERSION = "cbis-disclosure-v1"

INSTRUCTIONS = """Classify a Vietnamese corporate-bond disclosure for risk-surveillance enrichment.
Use ONLY the supplied text. Do not infer facts not stated in it.
Prefer OTHER_MATERIAL_DISCLOSURE when the text is ambiguous.
This output is an AI suggestion only; it must not overwrite deterministic source records automatically.
Use effective_date as YYYY-MM-DD when explicit, otherwise an empty string.
Return only the required structured fields."""


def _clip_text(text: str, max_chars: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= max_chars:
        return text
    # Preserve beginning and end, where titles/summary and legal/event dates often live.
    head = max_chars * 2 // 3
    tail = max_chars - head
    return text[:head] + " … [TRUNCATED] … " + text[-tail:]


def classify_disclosure(service: AIService, *, title: str, body_text: str = "", issuer_name: str = "",
                        source_url: str = "") -> AIResult:
    text_budget = max(500, service.policy.max_input_chars - 2500)
    payload = {
        "issuer_name": issuer_name,
        "title": title,
        "body_text": _clip_text(body_text, text_budget),
        "source_url": source_url,
    }
    return service.run_structured(
        feature="cbis_disclosure_classification",
        payload=payload,
        instructions=INSTRUCTIONS,
        schema_name="cbis_disclosure_classification",
        schema=DISCLOSURE_SCHEMA,
        prompt_version=PROMPT_VERSION,
        max_output_tokens=service.policy.disclosure_max_output_tokens,
    )
