from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from src.ingestion.sbv_omo import OmoRow, OMO_URL, PARSER_VERSION


def _deal_side(deal_type: str) -> str:
    folded = deal_type.lower()
    if "mua" in folded:
        return "INJECTION"
    if "bán" in folded or "ban" in folded:
        return "WITHDRAWAL"
    return "UNKNOWN"


def to_market_observations(
    rows: list[OmoRow],
    *,
    fetched_at: datetime,
    raw_path: str,
    raw_hash: str,
) -> list[dict]:
    processed_at = datetime.now(timezone.utc)
    out: list[dict] = []

    for row in rows:
        side = _deal_side(row.deal_type)
        entity_id = f"SBV_OMO:{side}:{row.tenor_days}D"
        dims = {
            "deal_type": row.deal_type,
            "side": side,
            "tenor_days": row.tenor_days,
            "maturity_date": row.maturity_date.isoformat(),
        }
        common = {
            "entity_type": "OMO_TENOR",
            "entity_id": entity_id,
            "period_start": row.session_date.isoformat(),
            "period_end": row.session_date.isoformat(),
            "as_of_time": None,
            "frequency": "SESSION",
            "source": "SBV",
            "source_url": OMO_URL,
            "source_published_at": None,
            "first_observed_at": fetched_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "processed_at": processed_at.isoformat(),
            "observation_method": "DIRECT_SOURCE",
            "quality_flag": "A",
            "raw_object_id": raw_path,
            "parser_version": PARSER_VERSION,
            "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
        }

        metrics = [
            ("SBV.OMO.VOLUME", row.volume_bn_vnd, "VND_bn", "FLOW"),
            ("SBV.OMO.RATE", row.rate_pct, "pct", "SNAPSHOT"),
            ("SBV.OMO.MEMBERS_BID", row.members_bid, "count", "FLOW"),
            ("SBV.OMO.MEMBERS_WON", row.members_won, "count", "FLOW"),
        ]
        for metric_id, value, unit, measure_type in metrics:
            if value is None:
                continue
            semantic_payload = {
                "source": "SBV",
                "metric_id": metric_id,
                "entity_id": entity_id,
                "period_end": row.session_date.isoformat(),
                "value": float(value),
                "unit": unit,
                "measure_type": measure_type,
                "maturity_date": row.maturity_date.isoformat(),
            }
            record_hash = hashlib.sha256(
                json.dumps(semantic_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            out.append(
                {
                    "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                    "metric_id": metric_id,
                    "value": float(value),
                    "unit": unit,
                    "measure_type": measure_type,
                    "record_hash": record_hash,
                    **common,
                }
            )
    return out
