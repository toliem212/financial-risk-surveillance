from __future__ import annotations


class ObservationValidationError(ValueError):
    pass


def validate_observation(obs: dict) -> list[str]:
    errors: list[str] = []
    required = [
        "observation_id", "metric_id", "entity_type", "entity_id", "value", "unit",
        "period_start", "period_end", "measure_type", "frequency", "source",
        "first_observed_at", "fetched_at", "processed_at", "observation_method",
        "quality_flag", "parser_version", "record_hash",
    ]
    for field in required:
        if obs.get(field) in (None, ""):
            errors.append(f"missing:{field}")

    if obs.get("quality_flag") not in {"A", "B", "C", "D", "X"}:
        errors.append("invalid:quality_flag")
    if obs.get("measure_type") not in {"SNAPSHOT", "FLOW", "STOCK", "AVERAGE", "INDEX", "EVENT"}:
        errors.append("invalid:measure_type")

    value = obs.get("value")
    if isinstance(value, (int, float)):
        if obs.get("metric_id") == "SBV.OMO.RATE" and not (0 <= float(value) <= 100):
            errors.append("implausible:rate_pct")
        if obs.get("metric_id") == "SBV.OMO.VOLUME" and float(value) < 0:
            errors.append("implausible:negative_volume")
        if obs.get("metric_id") in {"HNX.GOV.TRADE.YTM", "HNX.GOV.TENOR_YIELD", "HNX.GOV.AUCTION.YIELD"} and not (0 <= float(value) <= 30):
            errors.append("implausible:gov_yield_pct")
        if obs.get("metric_id", "").startswith("HNX.GOV.") and obs.get("unit") in {"VND", "count"} and float(value) < 0:
            errors.append("implausible:negative_hnx_value")
        if obs.get("metric_id") == "VIRA.IBOR.RATE" and not (0 <= float(value) <= 100):
            errors.append("implausible:vira_ibor_pct")
        if obs.get("metric_id") == "VIRA.GOV.YIELD" and not (0 <= float(value) <= 30):
            errors.append("implausible:vira_gov_yield_pct")
        if obs.get("metric_id") == "VIRA.OMO.REPO.RATE" and not (0 <= float(value) <= 100):
            errors.append("implausible:vira_omo_rate_pct")
        if obs.get("metric_id", "").startswith("VIRA.FX.") and not (1000 <= float(value) <= 100000):
            errors.append("implausible:vira_fx_vnd_per_usd")
        if obs.get("metric_id") in {"VIRA.OMO.REPO.TENDER", "VIRA.OMO.REPO.WIN", "VIRA.OMO.REPO.MATURITY", "VIRA.OMO.REPO.OUTSTANDING"} and float(value) < 0:
            errors.append("implausible:negative_vira_omo_amount")
        if obs.get("metric_id", "").startswith("SBV.MACRO."):
            if obs.get("unit") == "VND_bn" and float(value) < 0:
                errors.append("implausible:negative_sbv_macro_level")
            if obs.get("unit") == "pct" and not (-100 <= float(value) <= 300):
                errors.append("implausible:sbv_macro_pct")
    return errors


def validate_batch(observations: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for obs in observations:
        errors = validate_observation(obs)
        if errors:
            invalid.append({"observation": obs, "errors": errors})
        else:
            valid.append(obs)
    return valid, invalid
