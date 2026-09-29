from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from src.ingestion.sbv_macro import MacroRow, PARSER_VERSION, month_end


def _slug(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text.upper()[:80] or "TOTAL"


def to_market_observations(
    rows: list[MacroRow],
    *,
    fetched_at: datetime,
    raw_object_id: str,
    raw_hash: str,
    source_url: str,
) -> list[dict]:
    processed_at = datetime.now(timezone.utc)
    out: list[dict] = []
    for row in rows:
        period_start = row.reference_month
        period_end = month_end(period_start)
        label_slug = _slug(row.label)
        entity_id = f"SBV_MACRO:{row.page_id.upper()}:{label_slug}"
        common = {
            "entity_type": "MACRO_SERIES",
            "entity_id": entity_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "as_of_time": None,
            "frequency": "M",
            "source": "SBV",
            "source_url": source_url,
            # These SBV pages expose reference month but not a reliable publication timestamp.
            "source_published_at": None,
            "first_observed_at": fetched_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "processed_at": processed_at.isoformat(),
            "observation_method": "DIRECT_SOURCE",
            "quality_flag": "A",
            "raw_object_id": raw_object_id,
            "parser_version": PARSER_VERSION,
            "record_hash": "",
            "dims_json": json.dumps({"page_id": row.page_id, "label_vi": row.label}, ensure_ascii=False, sort_keys=True),
        }
        if row.level is not None:
            unit = "pct" if row.page_id == "ldr" else "VND_bn"
            measure = "SNAPSHOT" if row.page_id == "ldr" else "STOCK"
            metric = f"SBV.MACRO.{row.page_id.upper()}.LEVEL"
            payload = {"source": "SBV", "metric_id": metric, "entity_id": entity_id,
                       "period_end": period_end.isoformat(), "value": float(row.level),
                       "unit": unit, "measure_type": measure}
            record_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            row_common = dict(common, record_hash=record_hash)
            out.append({
                "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                "metric_id": metric,
                "value": float(row.level),
                "unit": unit,
                "measure_type": measure,
                **row_common,
            })
        if row.growth_ytd_pct is not None:
            metric = f"SBV.MACRO.{row.page_id.upper()}.GROWTH_YTD"
            payload = {"source": "SBV", "metric_id": metric, "entity_id": entity_id,
                       "period_end": period_end.isoformat(), "value": float(row.growth_ytd_pct),
                       "unit": "pct", "measure_type": "SNAPSHOT"}
            record_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            row_common = dict(common, record_hash=record_hash)
            out.append({
                "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                "metric_id": metric,
                "value": float(row.growth_ytd_pct),
                "unit": "pct",
                "measure_type": "SNAPSHOT",
                **row_common,
            })
    return out
