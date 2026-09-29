from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime, timezone

BASE_SEVERITY = {
    "PAYMENT_DELAY": "HIGH",
    "MATURITY_EXTENSION": "HIGH",
    "COLLATERAL_CHANGE": "HIGH",
    "TERM_CHANGE": "MEDIUM",
    "TRADING_SUSPENSION": "MEDIUM",
    "DELISTING": "INFO",
    "BUYBACK": "INFO",
    "PAYMENT_EVENT": "INFO",
    "REGISTRATION": "INFO",
    "RATING_OBSERVATION": "INFO",
    "OTHER_MATERIAL_DISCLOSURE": "INFO",
}


def _norm(value) -> str:
    s = str(value or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d")


def event_severity(event: dict) -> str:
    etype = event["event_type"]
    payload = event.get("event_payload") or {}
    # A trading suspension explicitly caused by an announced buyback is often a
    # mechanical lifecycle event, not evidence of market stress by itself.
    if etype == "TRADING_SUSPENSION" and "mua lai" in _norm(payload.get("reason")):
        return "INFO"
    return BASE_SEVERITY.get(etype, "LOW")


def event_signals(events: list[dict]) -> list[dict]:
    signals = []
    for e in events:
        sev = event_severity(e)
        # INFO events remain visible in the event timeline but do not clutter the alert inbox.
        if sev == "INFO":
            continue
        key = f"CB_EVENT|{e['event_hash']}|{e['event_type']}"
        signals.append({
            "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
            "signal_type": f"CB_{e['event_type']}",
            "domain": "CORPORATE_BOND",
            "entity_type": "BOND" if e.get("bond_id") else "ISSUER",
            "entity_id": e.get("bond_id") or e.get("issuer_id"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "current_value": None,
            "baseline_value": None,
            "absolute_change": None,
            "relative_change": None,
            "z_score": None,
            "percentile": None,
            "threshold": None,
            "severity": sev,
            "evidence_json": {
                "event_type": e["event_type"],
                "event_date": e.get("event_date"),
                "source": e["source"],
                "source_url": e.get("source_url"),
                "event_payload": e.get("event_payload"),
                "quality_flag": e.get("quality_flag"),
            },
            "status": "OPEN",
        })
    return signals
