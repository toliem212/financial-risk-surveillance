from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from src.signals.corporate_bond import event_signals
from src.signals.liquidity import build_omo_signals
from src.signals.rates import build_gov_yield_signals
from src.signals.fx import build_fx_signals

SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
STATE_BY_RANK = {0: "NORMAL", 1: "WATCH", 2: "ELEVATED", 3: "HIGH", 4: "HIGH"}


@dataclass
class ReplaySnapshot:
    cutoff: str
    mode: str
    observations: list[dict]
    events: list[dict]
    recorded_signals: list[dict]
    reconstructed_signals: list[dict]
    source_runs: list[dict]
    domain_state: dict[str, str]
    timeline: list[dict]


class ReplayObservationStore:
    """Small read-only store contract used by deterministic signal builders."""

    def __init__(self, observations: Iterable[dict]):
        self.rows = list(observations)

    def latest_observation(self, metric_id: str, entity_id: str, before_period: str | None = None):
        rows = [
            r for r in self.rows
            if r.get("metric_id") == metric_id and r.get("entity_id") == entity_id
            and (before_period is None or str(r.get("period_end")) < str(before_period))
        ]
        if not rows:
            return None
        rows.sort(key=lambda r: (str(r.get("period_end") or ""), str(r.get("fetched_at") or "")), reverse=True)
        return rows[0]


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {"raw": value}
    return value


def _latest_rows(rows: Iterable[dict], *, source: str | None = None) -> list[dict]:
    chosen: dict[tuple, dict] = {}
    for r in rows:
        if source is not None and r.get("source") != source:
            continue
        key = (r.get("source"), r.get("metric_id"), r.get("entity_id"))
        old = chosen.get(key)
        stamp = (str(r.get("period_end") or ""), str(r.get("fetched_at") or ""))
        old_stamp = (str(old.get("period_end") or ""), str(old.get("fetched_at") or "")) if old else None
        if old is None or stamp > old_stamp:
            chosen[key] = r
    return list(chosen.values())


def reconstruct_deterministic_signals(observation_history: list[dict], events: list[dict], thresholds: dict, cutoff: str) -> list[dict]:
    """Re-run deterministic rules using only rows eligible at the replay cutoff."""
    replay_store = ReplayObservationStore(observation_history)
    current = _latest_rows(observation_history)
    signals = []
    signals.extend(build_omo_signals([r for r in current if str(r.get("metric_id", "")).startswith("SBV.OMO")], replay_store, thresholds))
    signals.extend(build_gov_yield_signals([r for r in current if r.get("metric_id") == "HNX.GOV.TENOR_YIELD"], replay_store, thresholds))
    signals.extend(build_fx_signals([r for r in current if str(r.get("metric_id", "")).startswith("VIRA.FX.")], replay_store, thresholds))
    normalized_events = []
    for e in events:
        clean = dict(e)
        clean["event_payload"] = _json(clean.get("event_payload")) or {}
        normalized_events.append(clean)
    signals.extend(event_signals(normalized_events))
    for s in signals:
        s["generated_at"] = cutoff
        ev = _json(s.get("evidence_json")) or {}
        ev["replay_status"] = "RECONSTRUCTED_DETERMINISTIC"
        s["evidence_json"] = ev
    return signals


def domain_states(signals: Iterable[dict]) -> dict[str, str]:
    max_rank: dict[str, int] = {}
    for s in signals:
        domain = str(s.get("domain") or "OTHER")
        rank = SEVERITY_RANK.get(str(s.get("severity") or "INFO"), 0)
        max_rank[domain] = max(rank, max_rank.get(domain, 0))
    return {domain: STATE_BY_RANK[rank] for domain, rank in sorted(max_rank.items())}


def build_timeline(observations: list[dict], events: list[dict], signals: list[dict], limit: int = 250) -> list[dict]:
    items: list[dict] = []
    for r in observations:
        ts = r.get("first_observed_at") or r.get("source_published_at") or r.get("fetched_at")
        items.append({
            "timestamp": str(ts), "kind": "OBSERVATION", "domain": _domain_for_metric(r.get("metric_id")),
            "label": f"{r.get('metric_id')} / {r.get('entity_id')}", "value": r.get("value"),
            "quality_flag": r.get("quality_flag"), "source": r.get("source"),
        })
    for e in events:
        ts = e.get("first_observed_at") or e.get("announced_at")
        items.append({
            "timestamp": str(ts), "kind": "EVENT", "domain": "CORPORATE_BOND",
            "label": e.get("event_type"), "value": e.get("bond_id") or e.get("issuer_id"),
            "quality_flag": e.get("quality_flag"), "source": e.get("source"),
        })
    for s in signals:
        items.append({
            "timestamp": str(s.get("generated_at")), "kind": "SIGNAL", "domain": s.get("domain"),
            "label": s.get("signal_type"), "value": s.get("current_value"),
            "quality_flag": None, "source": "RULE_ENGINE", "severity": s.get("severity"),
        })
    items.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return items[:limit]


def _domain_for_metric(metric: str | None) -> str:
    m = str(metric or "")
    if m.startswith("SBV.OMO") or m.startswith("VIRA.OMO") or m.startswith("VIRA.IBOR"):
        return "LIQUIDITY"
    if ".FX." in m:
        return "FX"
    if "GOV" in m:
        return "RATES"
    return "OTHER"


def build_snapshot(store, cutoff: str, thresholds: dict, *, mode: str = "SYSTEM_KNOWN") -> ReplaySnapshot:
    mode = mode.upper()
    history = store.replay_observation_history(cutoff, mode=mode)
    latest = _latest_rows(history)
    events = store.replay_bond_events(cutoff, mode=mode)
    recorded = store.replay_recorded_signals(cutoff)
    source_runs = store.replay_source_runs(cutoff)
    reconstructed = reconstruct_deterministic_signals(history, events, thresholds, cutoff)
    state = domain_states(reconstructed)
    timeline = build_timeline(latest, events, reconstructed)
    return ReplaySnapshot(
        cutoff=cutoff, mode=mode, observations=latest, events=events,
        recorded_signals=recorded, reconstructed_signals=reconstructed,
        source_runs=source_runs, domain_state=state, timeline=timeline,
    )
