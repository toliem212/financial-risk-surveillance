from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _severity(change_bp: float, cfg: dict) -> str | None:
    x = abs(change_bp)
    if x >= float(cfg["high"]):
        return "HIGH"
    if x >= float(cfg["medium"]):
        return "MEDIUM"
    return None


def build_gov_yield_signals(current_observations: list[dict], store, thresholds: dict) -> list[dict]:
    cfg = thresholds["gov_yield_change_bp"]
    signals: list[dict] = []
    current_yields = [o for o in current_observations if o["metric_id"] == "HNX.GOV.TENOR_YIELD"]

    for obs in current_yields:
        prev = store.latest_observation(obs["metric_id"], obs["entity_id"], before_period=obs["period_end"])
        if not prev:
            continue
        current = float(obs["value"])
        baseline = float(prev["value"])
        change_bp = (current - baseline) * 100.0
        severity = _severity(change_bp, cfg)
        if not severity:
            continue
        key = f"YIELD_MOVE_HIGH|{obs['entity_id']}|{obs['period_end']}|{current}|{baseline}"
        signals.append({
            "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
            "signal_type": "YIELD_MOVE_HIGH",
            "domain": "RATES",
            "entity_type": obs["entity_type"],
            "entity_id": obs["entity_id"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "current_value": current,
            "baseline_value": baseline,
            "absolute_change": change_bp,
            "relative_change": None,
            "z_score": None,
            "percentile": None,
            "threshold": float(cfg["medium"]),
            "severity": severity,
            "evidence_json": {
                "current_period": obs["period_end"],
                "previous_period": prev["period_end"],
                "unit": "bp",
                "quality_flag": obs["quality_flag"],
                "curve_type": "derived_public_trade_curve",
            },
            "status": "OPEN",
        })

    # Curve slope: 10Y minus 5Y. Compare with prior day's matching observations.
    by_entity = {o["entity_id"]: o for o in current_yields}
    e5, e10 = "GOV_TENOR:5Y", "GOV_TENOR:10Y"
    if e5 in by_entity and e10 in by_entity:
        o5, o10 = by_entity[e5], by_entity[e10]
        p5 = store.latest_observation("HNX.GOV.TENOR_YIELD", e5, before_period=o5["period_end"])
        p10 = store.latest_observation("HNX.GOV.TENOR_YIELD", e10, before_period=o10["period_end"])
        if p5 and p10:
            current_slope_bp = (float(o10["value"]) - float(o5["value"])) * 100.0
            prev_slope_bp = (float(p10["value"]) - float(p5["value"])) * 100.0
            change_bp = current_slope_bp - prev_slope_bp
            scfg = thresholds["gov_curve_slope_change_bp"]
            severity = _severity(change_bp, scfg)
            if severity:
                signal_type = "CURVE_STEEPENING" if change_bp > 0 else "CURVE_FLATTENING"
                key = f"{signal_type}|5Y10Y|{o10['period_end']}|{current_slope_bp}|{prev_slope_bp}"
                signals.append({
                    "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                    "signal_type": signal_type,
                    "domain": "RATES",
                    "entity_type": "GOV_CURVE",
                    "entity_id": "GOV_CURVE:5Y10Y",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "current_value": current_slope_bp,
                    "baseline_value": prev_slope_bp,
                    "absolute_change": change_bp,
                    "relative_change": None,
                    "z_score": None,
                    "percentile": None,
                    "threshold": float(scfg["medium"]),
                    "severity": severity,
                    "evidence_json": {
                        "current_period": o10["period_end"],
                        "unit": "bp",
                        "curve_type": "derived_public_trade_curve",
                    },
                    "status": "OPEN",
                })
    return signals
