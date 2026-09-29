from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _severity(abs_change: float, medium: float, high: float) -> str | None:
    magnitude = abs(abs_change)
    if magnitude >= high:
        return "HIGH"
    if magnitude >= medium:
        return "MEDIUM"
    return None


def build_omo_signals(current_observations: list[dict], store, thresholds: dict) -> list[dict]:
    signals: list[dict] = []
    for obs in current_observations:
        metric = obs["metric_id"]
        if metric not in {"SBV.OMO.RATE", "SBV.OMO.VOLUME"}:
            continue
        prev = store.latest_observation(metric, obs["entity_id"], before_period=obs["period_end"])
        if not prev:
            continue

        current = float(obs["value"])
        baseline = float(prev["value"])
        if metric == "SBV.OMO.RATE":
            change = (current - baseline) * 100.0  # percentage point -> bp
            cfg = thresholds["omo_rate_change_bp"]
            signal_type = "OMO_RATE_CHANGE_HIGH"
            threshold = cfg["medium"]
        else:
            if baseline == 0:
                continue
            change = (current / baseline - 1.0) * 100.0
            cfg = thresholds["omo_volume_change_pct"]
            signal_type = "OMO_VOLUME_CHANGE_HIGH"
            threshold = cfg["medium"]

        severity = _severity(change, cfg["medium"], cfg["high"])
        if severity is None:
            continue

        key = f"{signal_type}|{obs['entity_id']}|{obs['period_end']}|{current}|{baseline}"
        signals.append({
            "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
            "signal_type": signal_type,
            "domain": "LIQUIDITY",
            "entity_type": obs["entity_type"],
            "entity_id": obs["entity_id"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "current_value": current,
            "baseline_value": baseline,
            "absolute_change": change,
            "relative_change": None,
            "z_score": None,
            "percentile": None,
            "threshold": threshold,
            "severity": severity,
            "evidence_json": {
                "current_period": obs["period_end"],
                "previous_period": prev["period_end"],
                "metric": metric,
                "quality_flag": obs["quality_flag"],
            },
            "status": "OPEN",
        })
    return signals
