from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from src.ingestion.hnx_gov import (
    AUCTION_PAGE,
    PARSER_VERSION,
    SECONDARY_PAGE,
    AuctionResult,
    SecondaryTrade,
    canonical_tenor,
)


def _row_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def secondary_to_observations(
    rows: list[SecondaryTrade], *, fetched_at: datetime, raw_path: str, raw_hash: str
) -> list[dict]:
    processed_at = datetime.now(timezone.utc)
    out: list[dict] = []

    # Trade-level observations preserve provenance.
    for i, row in enumerate(rows):
        tenor = canonical_tenor(row.remaining_tenor_raw)
        dims = {
            "bond_code": row.bond_code,
            "remaining_tenor_raw": row.remaining_tenor_raw,
            "canonical_tenor": tenor,
            "currency": row.currency,
            "price": row.price,
            "volume": row.volume,
            "trade_value_vnd": row.trade_value_vnd,
            "investor_type": row.investor_type,
            "trade_row": i,
        }
        if row.ytm_pct is not None:
            payload = {"metric": "HNX.GOV.TRADE.YTM", "date": row.trade_date.isoformat(), **dims, "value": row.ytm_pct}
            record_hash = _row_hash(payload)
            out.append({
                "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                "metric_id": "HNX.GOV.TRADE.YTM",
                "entity_type": "GOV_BOND",
                "entity_id": row.bond_code,
                "value": float(row.ytm_pct),
                "unit": "pct",
                "period_start": row.trade_date.isoformat(),
                "period_end": row.trade_date.isoformat(),
                "as_of_time": None,
                "measure_type": "SNAPSHOT",
                "frequency": "TRADE_DAY",
                "source": "HNX",
                "source_url": SECONDARY_PAGE,
                "source_published_at": None,
                "first_observed_at": fetched_at.isoformat(),
                "fetched_at": fetched_at.isoformat(),
                "processed_at": processed_at.isoformat(),
                "observation_method": "DIRECT_SOURCE",
                "quality_flag": "A",
                "raw_object_id": raw_path,
                "parser_version": PARSER_VERSION,
                "record_hash": record_hash,
                "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
            })

    # Derived public-market tenor curve. This is not the official HNX paid yield curve.
    grouped: dict[str, list[SecondaryTrade]] = defaultdict(list)
    for row in rows:
        tenor = canonical_tenor(row.remaining_tenor_raw)
        if tenor and row.ytm_pct is not None:
            grouped[tenor].append(row)

    for tenor, trades in grouped.items():
        weights = [t.trade_value_vnd if t.trade_value_vnd and t.trade_value_vnd > 0 else (t.volume or 0) for t in trades]
        if sum(weights) > 0:
            ytm = sum(float(t.ytm_pct) * w for t, w in zip(trades, weights)) / sum(weights)
            weight_basis = "trade_value_or_volume"
        else:
            ytm = sum(float(t.ytm_pct) for t in trades) / len(trades)
            weight_basis = "equal"
        turnover = sum((t.trade_value_vnd or 0.0) for t in trades)
        d = trades[0].trade_date
        dims = {
            "canonical_tenor": tenor,
            "trade_count": len(trades),
            "weight_basis": weight_basis,
            "derived_from": "public HNX outright trades",
            "official_hnx_yield_curve": False,
        }
        for metric_id, value, unit, measure_type in [
            ("HNX.GOV.TENOR_YIELD", ytm, "pct", "SNAPSHOT"),
            ("HNX.GOV.TENOR_TURNOVER", turnover, "VND", "FLOW"),
            ("HNX.GOV.TENOR_TRADE_COUNT", len(trades), "count", "FLOW"),
        ]:
            payload = {"metric": metric_id, "date": d.isoformat(), "tenor": tenor, "value": value}
            record_hash = _row_hash(payload)
            out.append({
                "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                "metric_id": metric_id,
                "entity_type": "GOV_TENOR",
                "entity_id": f"GOV_TENOR:{tenor}",
                "value": float(value),
                "unit": unit,
                "period_start": d.isoformat(),
                "period_end": d.isoformat(),
                "as_of_time": None,
                "measure_type": measure_type,
                "frequency": "DAILY",
                "source": "HNX",
                "source_url": SECONDARY_PAGE,
                "source_published_at": None,
                "first_observed_at": fetched_at.isoformat(),
                "fetched_at": fetched_at.isoformat(),
                "processed_at": processed_at.isoformat(),
                "observation_method": "DERIVED_CALCULATION",
                "quality_flag": "B" if metric_id == "HNX.GOV.TENOR_YIELD" else "A",
                "raw_object_id": raw_path,
                "parser_version": PARSER_VERSION,
                "record_hash": record_hash,
                "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
            })
    return out


def auctions_to_observations(
    rows: list[AuctionResult], *, fetched_at: datetime, raw_path: str, raw_hash: str
) -> list[dict]:
    processed_at = datetime.now(timezone.utc)
    out: list[dict] = []
    for row in rows:
        tenor = canonical_tenor(row.tenor_raw)
        dims = {
            "auction_round": row.auction_round,
            "bond_code": row.bond_code,
            "issue_type": row.issue_type,
            "tenor_raw": row.tenor_raw,
            "canonical_tenor": tenor,
            "additional_offered_value_vnd": row.additional_offered_value_vnd,
            "additional_bid_value_vnd": row.additional_bid_value_vnd,
            "additional_awarded_value_vnd": row.additional_awarded_value_vnd,
            "nominal_coupon_pct": row.nominal_coupon_pct,
            "registered_yield_low_pct": row.registered_yield_low_pct,
            "registered_yield_high_pct": row.registered_yield_high_pct,
        }
        metrics = [
            ("HNX.GOV.AUCTION.OFFERED_VALUE", row.offered_value_vnd, "VND", "FLOW"),
            ("HNX.GOV.AUCTION.BID_VALUE", row.bid_value_vnd, "VND", "FLOW"),
            ("HNX.GOV.AUCTION.AWARDED_VALUE", row.awarded_value_vnd, "VND", "FLOW"),
            ("HNX.GOV.AUCTION.YIELD", row.auction_yield_pct, "pct", "SNAPSHOT"),
        ]
        for metric_id, value, unit, measure_type in metrics:
            if value is None:
                continue
            payload = {
                "metric": metric_id,
                "date": row.auction_date.isoformat(),
                "bond": row.bond_code,
                "round": row.auction_round,
                "value": value,
            }
            record_hash = _row_hash(payload)
            out.append({
                "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
                "metric_id": metric_id,
                "entity_type": "GOV_AUCTION",
                "entity_id": f"GOV_AUCTION:{row.bond_code}",
                "value": float(value),
                "unit": unit,
                "period_start": row.auction_date.isoformat(),
                "period_end": row.auction_date.isoformat(),
                "as_of_time": None,
                "measure_type": measure_type,
                "frequency": "AUCTION",
                "source": "HNX",
                "source_url": AUCTION_PAGE,
                "source_published_at": None,
                "first_observed_at": fetched_at.isoformat(),
                "fetched_at": fetched_at.isoformat(),
                "processed_at": processed_at.isoformat(),
                "observation_method": "DIRECT_SOURCE",
                "quality_flag": "A",
                "raw_object_id": raw_path,
                "parser_version": PARSER_VERSION,
                "record_hash": record_hash,
                "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
            })
    return out
