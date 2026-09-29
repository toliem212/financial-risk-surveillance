from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from src.ingestion.hnx_cbonds import (
    BondRecord, DisclosureRecord, IssuerRecord, RatingRecord, TradingStatusRecord,
    normalize_issuer_name,
)


def issuer_id_for(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"HNX_CBIS_ISSUER|{normalize_issuer_name(name)}"))


def bond_id_for(code: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"HNX_CBIS_BOND|{code.strip().upper()}"))


def issuers_to_rows(records: list[IssuerRecord], observed_at: datetime) -> list[dict]:
    out = []
    ts = observed_at.isoformat()
    for r in records:
        out.append({
            "issuer_id": issuer_id_for(r.issuer_name),
            "issuer_code": r.issuer_code,
            "issuer_name": r.issuer_name,
            "normalized_name": normalize_issuer_name(r.issuer_name),
            "sector": r.sector,
            "charter_capital": r.charter_capital_vnd,
            "first_seen_at": ts,
            "last_seen_at": ts,
        })
    return out


def bonds_to_rows(records: list[BondRecord], observed_at: datetime) -> list[dict]:
    ts = observed_at.isoformat()
    out = []
    for r in records:
        canonical_code = (r.trading_code or r.disclosure_code).strip().upper()
        out.append({
            "bond_id": bond_id_for(canonical_code),
            "issuer_id": issuer_id_for(r.issuer_name),
            "disclosure_code": r.disclosure_code,
            "trading_code": r.trading_code,
            "isin": r.isin,
            "issuer_name": r.issuer_name,
            "face_value_vnd": r.face_value_vnd,
            "registered_quantity": r.registered_quantity,
            "registration_status": r.registration_status,
            "first_trade_date": r.first_trade_date.isoformat() if r.first_trade_date else None,
            "last_trade_date": r.last_trade_date.isoformat() if r.last_trade_date else None,
            "investor_scope": r.investor_scope,
            "first_seen_at": ts,
            "last_seen_at": ts,
        })
    return out


def _event_hash(payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classify_title(title: str) -> str:
    from src.ingestion.hnx_cbonds import _norm
    t = _norm(title)
    if "cham thanh toan" in t or "bi cham thanh toan" in t or "cham tra" in t:
        return "PAYMENT_DELAY"
    if "gia han" in t:
        return "MATURITY_EXTENSION"
    if "tai san bao dam" in t or "tai san dam bao" in t:
        return "COLLATERAL_CHANGE"
    if "thay doi dieu kien" in t or "thay doi dieu khoan" in t:
        return "TERM_CHANGE"
    if "mua lai" in t:
        return "BUYBACK"
    if "thanh toan goc" in t or "thanh toan lai" in t or "thanh toan goc, lai" in t:
        return "PAYMENT_EVENT"
    return "OTHER_MATERIAL_DISCLOSURE"


def disclosures_to_events(records: list[DisclosureRecord], observed_at: datetime) -> list[dict]:
    out = []
    for r in records:
        etype = _classify_title(r.title)
        # Periodic reports are kept only if the title itself maps to a specific risk event.
        if r.category == "PERIODIC" and etype == "OTHER_MATERIAL_DISCLOSURE":
            continue
        codes = r.bond_codes or (None,)
        for code in codes:
            payload = {
                "title": r.title,
                "category": r.category,
                "status": r.status,
                "bond_code": code,
            }
            eh = _event_hash({"source": "HNX_CBIS", "published": str(r.published_date), "issuer": r.issuer_name, **payload})
            out.append({
                "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"CBIS_EVENT|{eh}")),
                "issuer_id": issuer_id_for(r.issuer_name),
                "bond_id": bond_id_for(code) if code else None,
                "event_type": etype,
                "event_date": r.published_date.isoformat() if r.published_date else None,
                "effective_date": None,
                "announced_at": None,
                "first_observed_at": observed_at.isoformat(),
                "source": "HNX_CBIS",
                "source_url": r.source_url,
                "event_payload": payload,
                "quality_flag": "A",
                "event_hash": eh,
            })
    return out


def trading_status_to_events(records: list[TradingStatusRecord], observed_at: datetime) -> list[dict]:
    from src.ingestion.hnx_cbonds import _norm
    out = []
    for r in records:
        t = _norm(r.title)
        if "tam ngung giao dich" in t:
            etype = "TRADING_SUSPENSION"
        elif "huy bo dang ky giao dich" in t or "huy dang ky giao dich" in t:
            etype = "DELISTING"
        elif "dang ky giao dich" in t:
            etype = "REGISTRATION"
        else:
            continue
        canonical_code = r.trading_code or r.disclosure_code
        payload = {
            "title": r.title,
            "reason": r.reason,
            "status": r.status,
            "disclosure_code": r.disclosure_code,
            "trading_code": r.trading_code,
        }
        eh = _event_hash({"source": "HNX_CBIS", "effective": str(r.effective_date), "issuer": r.issuer_name, **payload})
        out.append({
            "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"CBIS_EVENT|{eh}")),
            "issuer_id": issuer_id_for(r.issuer_name),
            "bond_id": bond_id_for(canonical_code) if canonical_code else None,
            "event_type": etype,
            "event_date": r.effective_date.isoformat() if r.effective_date else None,
            "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            "announced_at": None,
            "first_observed_at": observed_at.isoformat(),
            "source": "HNX_CBIS",
            "source_url": r.source_url,
            "event_payload": payload,
            "quality_flag": "A",
            "event_hash": eh,
        })
    return out


def ratings_to_events(records: list[RatingRecord], observed_at: datetime) -> list[dict]:
    out = []
    for r in records:
        payload = {
            "agency": r.agency,
            "subject_type": r.subject_type,
            "rating": r.rating,
            "rating_type": r.rating_type,
            "bond_code": r.bond_code,
        }
        eh = _event_hash({"source": "HNX_CBIS", "effective": str(r.effective_date), "issuer": r.issuer_name, **payload})
        out.append({
            "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"CBIS_EVENT|{eh}")),
            "issuer_id": issuer_id_for(r.issuer_name),
            "bond_id": bond_id_for(r.bond_code) if r.bond_code else None,
            "event_type": "RATING_OBSERVATION",
            "event_date": r.effective_date.isoformat() if r.effective_date else None,
            "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            "announced_at": None,
            "first_observed_at": observed_at.isoformat(),
            "source": "HNX_CBIS",
            "source_url": "https://cbonds.hnx.vn/danh-sach-thong-tin-xep-hang-tin-nhiem",
            "event_payload": payload,
            "quality_flag": "A",
            "event_hash": eh,
        })
    return out
