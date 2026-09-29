from __future__ import annotations

INVESTIGATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "what_changed": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "data_quality_note": {"type": "string"},
        "possible_transmission": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "monitor_next": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "caveats": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": [
        "summary", "what_changed", "why_it_matters", "data_quality_note",
        "possible_transmission", "monitor_next", "caveats",
    ],
}

DISCLOSURE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "event_type": {
            "type": "string",
            "enum": [
                "PAYMENT_DELAY", "MATURITY_EXTENSION", "TERM_CHANGE", "COLLATERAL_CHANGE",
                "BUYBACK", "PAYMENT_EVENT", "RATING_OBSERVATION", "TRADING_SUSPENSION",
                "DELISTING", "REGISTRATION", "OTHER_MATERIAL_DISCLOSURE",
            ],
        },
        "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "reason": {"type": "string"},
        "bond_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "effective_date": {"type": "string"},
        "material_terms_changed": {"type": "boolean"},
        "requires_human_review": {"type": "boolean"},
    },
    "required": [
        "event_type", "confidence", "reason", "bond_codes", "effective_date",
        "material_terms_changed", "requires_human_review",
    ],
}
