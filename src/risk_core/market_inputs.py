from __future__ import annotations

from datetime import date
from typing import Any


MAX_YIELD_HISTORY_GAP_DAYS = 7
MAX_ABS_DAILY_YIELD_MOVE_BP = 100.0


def _as_dict(row):
    if row is None:
        return None
    return dict(row)


def assess_yield_change(current, previous) -> dict:
    """Validate a tenor-yield change before it is used for risk P&L."""
    current = _as_dict(current)
    previous = _as_dict(previous)

    result = {
        "previous_value_pct": None,
        "previous_period_end": None,
        "raw_change_bp": None,
        "validated_change_bp": None,
        "dq_status": "INSUFFICIENT_HISTORY",
        "dq_reason": "No previous comparable observation.",
    }

    if current is None:
        result["dq_status"] = "MISSING_CURRENT"
        result["dq_reason"] = "No current market observation."
        return result

    if previous is None:
        return result

    result["previous_value_pct"] = float(previous["value"])
    result["previous_period_end"] = previous.get("period_end")

    if str(current.get("metric_id")) != str(previous.get("metric_id")):
        result["dq_status"] = "SOURCE_MISMATCH"
        result["dq_reason"] = "Current and previous observations use different metric definitions."
        return result

    if str(current.get("entity_id")) != str(previous.get("entity_id")):
        result["dq_status"] = "SOURCE_MISMATCH"
        result["dq_reason"] = "Current and previous observations refer to different tenors/entities."
        return result

    if str(current.get("source")) != str(previous.get("source")):
        result["dq_status"] = "SOURCE_MISMATCH"
        result["dq_reason"] = "Current and previous observations come from different sources."
        return result

    try:
        current_date = date.fromisoformat(str(current["period_end"])[:10])
        previous_date = date.fromisoformat(str(previous["period_end"])[:10])
        gap_days = (current_date - previous_date).days
    except Exception:
        result["dq_status"] = "INVALID_DATE"
        result["dq_reason"] = "Observation dates cannot be validated."
        return result

    if gap_days <= 0:
        result["dq_status"] = "INVALID_SEQUENCE"
        result["dq_reason"] = "Previous observation is not earlier than the current observation."
        return result

    if gap_days > MAX_YIELD_HISTORY_GAP_DAYS:
        result["dq_status"] = "STALE_HISTORY"
        result["dq_reason"] = (
            f"Previous comparable observation is {gap_days} calendar days old; "
            f"maximum allowed is {MAX_YIELD_HISTORY_GAP_DAYS}."
        )
        return result

    change_bp = (float(current["value"]) - float(previous["value"])) * 100.0
    result["raw_change_bp"] = change_bp

    if abs(change_bp) > MAX_ABS_DAILY_YIELD_MOVE_BP:
        result["dq_status"] = "OUTLIER_REVIEW"
        result["dq_reason"] = (
            f"Absolute yield move {abs(change_bp):.1f} bp exceeds the "
            f"{MAX_ABS_DAILY_YIELD_MOVE_BP:.0f} bp MVP review threshold."
        )
        return result

    result["validated_change_bp"] = change_bp
    result["dq_status"] = "VALID"
    result["dq_reason"] = "Comparable observation passed the market-data quality gate."
    return result


def _latest_map(store, limit: int = 5000) -> list[dict[str, Any]]:
    rows = store.latest_observations(limit)
    return [dict(r) for r in rows]


def _pick(rows: list[dict], metric_id: str, entity_id: str | None = None, *, source: str | None = None):
    candidates = [r for r in rows if str(r.get("metric_id")) == metric_id]
    if entity_id is not None:
        candidates = [r for r in candidates if str(r.get("entity_id")) == entity_id]
    if source is not None:
        candidates = [r for r in candidates if str(r.get("source")) == source]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (str(r.get("period_end") or ""), str(r.get("fetched_at") or "")), reverse=True)
    return candidates[0]


def _previous(store, row: dict | None):
    if not row:
        return None
    return store.latest_observation(
        str(row["metric_id"]),
        str(row["entity_id"]),
        before_period=str(row["period_end"]),
    )


def latest_market_inputs(store) -> dict:
    rows = _latest_map(store)

    fx = _pick(rows, "VIRA.FX.INTERBANK")
    fx_prev = _previous(store, fx)

    gov: dict[str, dict] = {}
    for tenor in ("5Y", "10Y", "15Y"):
        entity = f"GOV_TENOR:{tenor}"
        row = _pick(rows, "HNX.GOV.TENOR_YIELD", entity)
        if row is None:
            row = _pick(rows, "VIRA.GOV.YIELD", entity)
        prev = _previous(store, row)
        dq = assess_yield_change(row, prev)

        gov[tenor] = {
            "value_pct": float(row["value"]) if row else None,
            "period_end": row.get("period_end") if row else None,
            "source": row.get("source") if row else None,
            "quality_flag": row.get("quality_flag") if row else None,
            "previous_value_pct": dq["previous_value_pct"],
            "previous_period_end": dq["previous_period_end"],
            "raw_change_bp": dq["raw_change_bp"],
            "change_bp": dq["validated_change_bp"],
            "dq_status": dq["dq_status"],
            "dq_reason": dq["dq_reason"],
        }

    ibor_on = _pick(rows, "VIRA.IBOR.RATE", "IBOR:VND:ON")

    # Prefer a primary-source SBV session aggregate when current tenor rows are available.
    sbv_omo = [r for r in rows if str(r.get("metric_id")) == "SBV.OMO.VOLUME"]
    omo_net_value = None
    omo_net_source = None
    if sbv_omo:
        latest_omo_date = max(str(r.get("period_end") or "") for r in sbv_omo)
        current = [r for r in sbv_omo if str(r.get("period_end") or "") == latest_omo_date]
        signed = []
        for r in current:
            entity = str(r.get("entity_id") or "")
            value = float(r.get("value") or 0.0)
            if ":INJECTION:" in entity:
                signed.append(value)
            elif ":WITHDRAWAL:" in entity:
                signed.append(-value)
        if signed:
            omo_net_value = sum(signed)
            omo_net_source = "SBV"
    if omo_net_value is None:
        vira_omo_net = _pick(rows, "VIRA.OMO.REPO.NET")
        if vira_omo_net:
            omo_net_value = float(vira_omo_net["value"])
            omo_net_source = "VIRA"

    omo_outstanding = _pick(rows, "VIRA.OMO.REPO.OUTSTANDING")

    fx_change_pct = None
    if fx and fx_prev and float(fx_prev["value"]) != 0:
        fx_change_pct = (float(fx["value"]) / float(fx_prev["value"]) - 1.0) * 100.0

    return {
        "fx_usd_vnd": {
            "spot": float(fx["value"]) if fx else None,
            "period_end": fx.get("period_end") if fx else None,
            "source": fx.get("source") if fx else None,
            "quality_flag": fx.get("quality_flag") if fx else None,
            "daily_change_pct": fx_change_pct,
        },
        "gov_yields": gov,
        "ibor_vnd_on": {
            "rate_pct": float(ibor_on["value"]) if ibor_on else None,
            "period_end": ibor_on.get("period_end") if ibor_on else None,
            "source": ibor_on.get("source") if ibor_on else None,
        },
        "omo_net": omo_net_value,
        "omo_net_source": omo_net_source,
        "omo_outstanding": float(omo_outstanding["value"]) if omo_outstanding else None,
    }
