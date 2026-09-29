from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _severity_abs(value: float, cfg: dict) -> str | None:
    x = abs(float(value))
    if x >= float(cfg["high"]):
        return "HIGH"
    if x >= float(cfg["medium"]):
        return "MEDIUM"
    return None


def build_fx_signals(current_observations: list[dict], store, thresholds: dict) -> list[dict]:
    """Build deterministic FX surveillance signals from normalized public observations.

    MVP rules deliberately use only observable market levels. They do not forecast FX and
    do not treat the SBV selling rate as an interbank trading ceiling. It is labelled only
    as a policy/reference level.
    """
    rows = [r for r in current_observations if str(r.get("metric_id", "")).startswith("VIRA.FX.")]
    by_metric = {}
    for r in rows:
        old = by_metric.get(r["metric_id"])
        stamp = (str(r.get("period_end") or ""), str(r.get("fetched_at") or ""))
        old_stamp = (str(old.get("period_end") or ""), str(old.get("fetched_at") or "")) if old else None
        if old is None or stamp > old_stamp:
            by_metric[r["metric_id"]] = r
    interbank = by_metric.get("VIRA.FX.INTERBANK")
    if not interbank:
        return []

    now = datetime.now(timezone.utc).isoformat()
    signals: list[dict] = []
    current = float(interbank["value"])

    # 1) Daily/end-of-week market move versus the prior available observation.
    prev = store.latest_observation("VIRA.FX.INTERBANK", interbank["entity_id"], before_period=interbank["period_end"])
    if prev and float(prev["value"]) != 0:
        baseline = float(prev["value"])
        move_pct = (current / baseline - 1.0) * 100.0
        cfg = thresholds["fx_daily_move_pct"]
        severity = _severity_abs(move_pct, cfg)
        if severity:
            key = f"FX_MOVE_HIGH|{interbank['period_end']}|{current}|{baseline}"
            signals.append({
                "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                "signal_type": "FX_MOVE_HIGH",
                "domain": "FX",
                "entity_type": interbank["entity_type"],
                "entity_id": interbank["entity_id"],
                "generated_at": now,
                "current_value": current,
                "baseline_value": baseline,
                "absolute_change": current - baseline,
                "relative_change": move_pct,
                "z_score": None,
                "percentile": None,
                "threshold": float(cfg["medium"]),
                "severity": severity,
                "evidence_json": {
                    "metric": "VIRA.FX.INTERBANK",
                    "current_period": interbank["period_end"],
                    "previous_period": prev["period_end"],
                    "move_pct": move_pct,
                    "quality_flag": interbank.get("quality_flag"),
                    "source": interbank.get("source"),
                },
                "status": "OPEN",
            })

    # 2) Proximity to the SBV selling reference published in the same source snapshot.
    sbv_sell = by_metric.get("VIRA.FX.SBV_SELL")
    if sbv_sell and float(sbv_sell["value"]) > 0:
        reference = float(sbv_sell["value"])
        distance_pct = (reference - current) / reference * 100.0
        cfg = thresholds["fx_policy_reference_proximity_pct"]
        # Smaller distance means greater proximity. A value <= 0 means the observed
        # interbank level is at/above this reference; flag HIGH without calling it a cap.
        severity = None
        if distance_pct <= float(cfg["high"]):
            severity = "HIGH"
        elif distance_pct <= float(cfg["medium"]):
            severity = "MEDIUM"
        if severity:
            key = f"FX_POLICY_REFERENCE_PROXIMITY|{interbank['period_end']}|{current}|{reference}"
            signals.append({
                "signal_id": str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                "signal_type": "FX_POLICY_REFERENCE_PROXIMITY",
                "domain": "FX",
                "entity_type": "FX_MARKET",
                "entity_id": "USDVND",
                "generated_at": now,
                "current_value": current,
                "baseline_value": reference,
                "absolute_change": reference - current,
                "relative_change": distance_pct,
                "z_score": None,
                "percentile": None,
                "threshold": float(cfg["medium"]),
                "severity": severity,
                "evidence_json": {
                    "metric": "VIRA.FX.INTERBANK",
                    "reference_metric": "VIRA.FX.SBV_SELL",
                    "reference_label": "SBV selling reference",
                    "period_end": interbank["period_end"],
                    "distance_pct": distance_pct,
                    "quality_flag": interbank.get("quality_flag"),
                    "source": interbank.get("source"),
                    "guardrail": "Reference proximity only; not labelled as an interbank trading ceiling.",
                },
                "status": "OPEN",
            })

    return signals
