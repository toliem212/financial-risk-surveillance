from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone

ADDITIVE_WEEKLY_METRICS = {
    "VIRA.OMO.REPO.TENDER",
    "VIRA.OMO.REPO.WIN",
    "VIRA.OMO.REPO.MATURITY",
    "VIRA.OMO.REPO.NET",
}


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _dims(row: dict) -> dict:
    raw = row.get("dims_json")
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw_dims": str(raw)}


def derive_friday_residual(weekly_obs: dict, daily_obs: list[dict]) -> dict | None:
    """Derive Friday only for additive weekly FLOW metrics.

    Strict MVP rule: Monday-Thursday must each have exactly one DIRECT_DAILY observation,
    Friday must be the weekly period_end, and no direct Friday observation may exist.
    Holiday-aware calendars are deferred; ambiguity returns None rather than inventing data.
    """
    if weekly_obs.get("metric_id") not in ADDITIVE_WEEKLY_METRICS:
        return None
    if weekly_obs.get("measure_type") != "FLOW" or weekly_obs.get("observation_method") != "WEEKLY_AGGREGATE":
        return None

    week_start = date.fromisoformat(str(weekly_obs["period_start"]))
    week_end = date.fromisoformat(str(weekly_obs["period_end"]))
    if (week_end - week_start).days != 4:
        return None

    relevant = [
        r for r in daily_obs
        if r.get("metric_id") == weekly_obs.get("metric_id")
        and r.get("entity_id") == weekly_obs.get("entity_id")
        and r.get("source") == "VIRA"
        and r.get("observation_method") == "DIRECT_DAILY"
    ]
    by_date: dict[date, list[dict]] = {}
    for row in relevant:
        d = date.fromisoformat(str(row["period_end"]))
        by_date.setdefault(d, []).append(row)

    if by_date.get(week_end):
        return None

    required = [week_start + timedelta(days=i) for i in range(4)]
    if any(len(by_date.get(d, [])) != 1 for d in required):
        return None

    components = [by_date[d][0] for d in required]
    residual = float(weekly_obs["value"]) - sum(float(r["value"]) for r in components)
    if weekly_obs["metric_id"] != "VIRA.OMO.REPO.NET" and residual < -1e-9:
        return None
    if abs(residual) < 1e-9:
        residual = 0.0

    now = datetime.now(timezone.utc)
    dims = _dims(weekly_obs)
    dims.update({
        "derived_from_weekly_observation_id": weekly_obs.get("observation_id"),
        "component_observation_ids": [r.get("observation_id") for r in components],
        "derivation": "weekly_total_minus_mon_thu",
        "strict_calendar_rule": "Mon-Thu required; holiday ambiguity not inferred",
    })
    payload = {
        "metric_id": weekly_obs["metric_id"],
        "entity_id": weekly_obs["entity_id"],
        "period": week_end.isoformat(),
        "residual": residual,
        "components": [r.get("record_hash") for r in components],
        "weekly_hash": weekly_obs.get("record_hash"),
    }
    record_hash = _hash(payload)
    return {
        "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
        "metric_id": weekly_obs["metric_id"],
        "entity_type": weekly_obs["entity_type"],
        "entity_id": weekly_obs["entity_id"],
        "value": residual,
        "unit": weekly_obs["unit"],
        "period_start": week_end.isoformat(),
        "period_end": week_end.isoformat(),
        "as_of_time": None,
        "measure_type": "FLOW",
        "frequency": "DAILY",
        "source": "VIRA",
        "source_url": weekly_obs.get("source_url"),
        "source_published_at": weekly_obs.get("source_published_at"),
        "first_observed_at": weekly_obs.get("first_observed_at") or now.isoformat(),
        "fetched_at": weekly_obs.get("fetched_at") or now.isoformat(),
        "processed_at": now.isoformat(),
        "observation_method": "DERIVED_RESIDUAL",
        "quality_flag": "B",
        "raw_object_id": weekly_obs.get("raw_object_id"),
        "parser_version": weekly_obs.get("parser_version") or "vira-semantic-v1",
        "record_hash": record_hash,
        "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
    }


def reconcile_with_primary(observations: list[dict], store, *, gov_tolerance_bp: float = 5.0, omo_tolerance_bn: float = 1.0):
    """Enrich VIRA observations with deterministic cross-source reconciliation.

    Supported MVP matches:
      - VIRA.GOV.YIELD vs HNX.GOV.TENOR_YIELD, same tenor/date.
      - VIRA daily OMO repo WIN vs sum of SBV OMO injection volumes, same date.

    Returns (enriched_observations, data_quality_signals).
    """
    enriched: list[dict] = []
    signals: list[dict] = []
    now = datetime.now(timezone.utc)

    for row in observations:
        r = dict(row)
        dims = _dims(r)
        status = None
        reference = None
        tolerance = None
        diff = None

        if r.get("metric_id") == "VIRA.GOV.YIELD":
            primary = store.observations_for_period(
                metric_id="HNX.GOV.TENOR_YIELD",
                entity_id=r.get("entity_id"),
                period_end=str(r.get("period_end")),
                source="HNX",
            )
            if primary:
                reference = float(primary[0]["value"])
                diff = float(r["value"]) - reference
                tolerance = gov_tolerance_bp / 100.0

        elif r.get("metric_id") == "VIRA.OMO.REPO.WIN" and r.get("observation_method") == "DIRECT_DAILY":
            primary = store.observations_for_period(
                metric_id="SBV.OMO.VOLUME",
                entity_id=None,
                period_end=str(r.get("period_end")),
                source="SBV",
            )
            injection = []
            for p in primary:
                pdims = _dims(p)
                if pdims.get("side") == "INJECTION":
                    injection.append(p)
            if injection:
                reference = sum(float(p["value"]) for p in injection)
                diff = float(r["value"]) - reference
                tolerance = omo_tolerance_bn

        if reference is not None and diff is not None and tolerance is not None:
            status = "MATCH" if abs(diff) <= tolerance else "MISMATCH"
            dims["reconciliation"] = {
                "status": status,
                "reference_value": reference,
                "difference": diff,
                "tolerance": tolerance,
                "primary_source": "HNX" if r["metric_id"] == "VIRA.GOV.YIELD" else "SBV",
            }
            if status == "MATCH":
                r["quality_flag"] = "B"
            else:
                # VIRA remains a usable secondary observation but requires review.
                r["quality_flag"] = "D"
                signal_key = f"{r['metric_id']}|{r['entity_id']}|{r['period_end']}|{diff}"
                signal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, signal_key))
                signals.append({
                    "signal_id": signal_id,
                    "signal_type": "SOURCE_MISMATCH",
                    "domain": "DATA_QUALITY",
                    "entity_type": r.get("entity_type"),
                    "entity_id": r.get("entity_id"),
                    "generated_at": now.isoformat(),
                    "current_value": float(r["value"]),
                    "baseline_value": reference,
                    "absolute_change": diff,
                    "relative_change": (diff / reference) if reference else None,
                    "z_score": None,
                    "percentile": None,
                    "threshold": tolerance,
                    "severity": "MEDIUM",
                    "evidence_json": {
                        "secondary_source": "VIRA",
                        "metric_id": r["metric_id"],
                        "period_end": r["period_end"],
                        "tolerance": tolerance,
                    },
                    "status": "OPEN",
                })

        r["dims_json"] = json.dumps(dims, ensure_ascii=False, sort_keys=True)
        enriched.append(r)
    return enriched, signals
