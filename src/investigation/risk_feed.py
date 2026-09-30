from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src.signals.corporate_bond import event_severity

SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

RELATED_PREFIXES = {
    "LIQUIDITY": ("SBV.OMO", "VIRA.OMO", "VIRA.IBOR", "VIRA.FX.INTERBANK", "HNX.GOV.TENOR_YIELD"),
    "FX": ("VIRA.FX", "VIRA.IBOR", "SBV.OMO", "HNX.GOV.TENOR_YIELD"),
    "RATES": ("HNX.GOV", "VIRA.GOV", "VIRA.IBOR", "SBV.OMO", "VIRA.FX.INTERBANK"),
    "CORPORATE_BOND": ("HNX.GOV", "VIRA.IBOR", "SBV.OMO", "VIRA.FX.INTERBANK"),
    "DATA_QUALITY": ("VIRA.", "SBV.", "HNX."),
}

TRANSMISSION = {
    "LIQUIDITY": [
        "Điều kiện vốn ngắn hạn có thể truyền sang lãi suất liên ngân hàng theo kỳ hạn và chi phí vốn của ngân hàng.",
        "Thanh khoản thắt chặt kéo dài có thể đi cùng áp lực ở đầu ngắn của đường cong TPCP.",
        "Khi diễn giải thay đổi OMO cần kiểm tra đồng thời điều kiện thanh khoản và FX, không suy diễn quan hệ nhân quả chỉ từ đồng biến.",
    ],
    "FX": [
        "Áp lực FX có thể tương tác với thanh khoản và hoạt động điều hành; không mặc định chiều nhân quả chỉ từ đồng biến.",
        "Biến động FX lớn có thể làm thay đổi valuation và rủi ro của vị thế ngoại hối mở trong trading book.",
        "Cần kiểm tra lãi suất và thanh khoản có xác nhận hay mâu thuẫn với tín hiệu FX trước khi kết luận rộng hơn.",
    ],
    "RATES": [
        "Tái định giá đường cong lợi suất có thể làm thay đổi mark-to-market và PV01/DV01 của danh mục fixed income.",
        "Biến động đầu ngắn có thể gắn với tiền tệ/thanh khoản, còn đầu dài phản ánh thêm duration và rủi ro vĩ mô.",
        "Cần phân biệt bằng chứng từ đấu thầu sơ cấp với giao dịch thứ cấp khi diễn giải cung-cầu.",
    ],
    "CORPORATE_BOND": [
        "Sự kiện trái phiếu có thể làm thay đổi bối cảnh tái cấp vốn, kỳ hạn, thanh khoản hoặc rủi ro điều khoản của issuer/bond liên quan.",
        "Mức độ cần được đọc cùng thanh khoản giao dịch, khoảng cách đến đáo hạn và nội dung disclosure cụ thể.",
        "Sự kiện công khai không chứng minh bất kỳ ngân hàng cụ thể nào đang nắm giữ hoặc có direct exposure với trái phiếu đó.",
    ],
    "DATA_QUALITY": [
        "Cần xử lý bất nhất nguồn/dữ liệu trước khi diễn giải chỉ tiêu rủi ro bị ảnh hưởng.",
        "Mismatch có thể đến từ khác biệt timing, định nghĩa, đơn vị hoặc parser chứ không nhất thiết là rủi ro kinh tế thực.",
    ],
}


MONITOR_NEXT = {
    "LIQUIDITY": ["Kết quả OMO tiếp theo và lịch đáo hạn", "Cấu trúc kỳ hạn O/N–1W–1M", "Phản ứng của FX và TPCP đầu ngắn"],
    "FX": ["USD/VND liên ngân hàng ở các quan sát tiếp theo", "Khoảng cách tới các mức tham chiếu điều hành", "O/N/term rates và xác nhận từ thị trường lãi suất"],
    "RATES": ["Biến động các kỳ hạn lân cận và độ rộng của đường cong", "Thanh khoản/doanh số thứ cấp", "Nhu cầu đấu thầu và bối cảnh tiền tệ"],
    "CORPORATE_BOND": ["Disclosure tiếp theo của issuer", "Thay đổi trạng thái giao dịch", "Rating/payment/maturity event của cùng issuer hoặc bond"],
    "DATA_QUALITY": ["Xác nhận lại nguồn primary", "Sức khỏe parser/source-run", "Mismatch có tiếp diễn sau lần ingest kế tiếp hay không"],
}



def _json(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            return {"raw": value}
    return {"value": value}


def _signal_title(signal: dict) -> str:
    names = {
        "OMO_RATE_CHANGE_HIGH": "Lãi suất OMO biến động đáng kể",
        "OMO_VOLUME_CHANGE_HIGH": "Khối lượng OMO biến động đáng kể",
        "YIELD_MOVE_HIGH": "Lợi suất TPCP biến động đáng kể",
        "CURVE_STEEPENING": "Đường cong lợi suất TPCP dốc lên",
        "CURVE_FLATTENING": "Đường cong lợi suất TPCP phẳng hơn",
        "FX_MOVE_HIGH": "USD/VND liên ngân hàng biến động mạnh",
        "FX_POLICY_REFERENCE_PROXIMITY": "USD/VND tiến gần mức tham chiếu điều hành của NHNN",
        "SOURCE_MISMATCH": "Sai lệch khi đối chiếu nguồn công khai",
    }
    typ = str(signal.get("signal_type") or "")
    if typ.startswith("CB_"):
        key = typ.removeprefix("CB_")
        cb_names = {
            "PAYMENT_DELAY": "Chậm thanh toán (Payment Delay)",
            "MATURITY_EXTENSION": "Gia hạn kỳ hạn (Maturity Extension)",
            "COLLATERAL_CHANGE": "Thay đổi tài sản bảo đảm (Collateral Change)",
            "TERM_CHANGE": "Thay đổi điều khoản (Term Change)",
            "TRADING_SUSPENSION": "Tạm ngừng giao dịch (Trading Suspension)",
            "EARLY_REDEMPTION": "Mua lại trước hạn (Early Redemption)",
            "RATING_DOWNGRADE": "Hạ xếp hạng tín nhiệm (Rating Downgrade)",
        }
        return cb_names.get(key, key.replace("_", " ").title())
    return names.get(typ, typ.replace("_", " ").title())


def build_risk_feed(store, *, signal_limit: int = 200, event_limit: int = 100, limit: int = 200) -> list[dict]:
    signals = store.recent_signals(signal_limit)
    items: list[dict] = []
    for s in signals:
        evidence = _json(s.get("evidence_json"))
        generated_at = str(s.get("generated_at") or "")
        market_date = str(
            evidence.get("current_period")
            or evidence.get("period_end")
            or generated_at[:10]
            or ""
        )
        items.append({
            "feed_id": f"signal:{s['signal_id']}",
            "item_type": "SIGNAL",
            "timestamp": market_date,
            "event_date": None,
            "generated_at": generated_at,
            "severity": str(s.get("severity") or "INFO"),
            "domain": str(s.get("domain") or "OTHER"),
            "signal_type": str(s.get("signal_type") or ""),
            "title": _signal_title(s),
            "entity_id": s.get("entity_id"),
            "source": evidence.get("source") or evidence.get("secondary_source") or "RULE_ENGINE",
            "status": str(s.get("status") or "OPEN"),
            "signal_id": s["signal_id"],
            "event_id": None,
        })

    # Keep lifecycle/info events in the feed even when they intentionally do not create alerts.
    for e in store.recent_bond_events(event_limit):
        clean = dict(e)
        clean["event_payload"] = _json(clean.get("event_payload"))
        sev = event_severity(clean)
        if sev != "INFO":
            continue
        observed_date = str(
            e.get("announced_at")
            or e.get("first_observed_at")
            or ""
        )[:10]
        event_date = str(
            e.get("event_date")
            or e.get("effective_date")
            or ""
        )[:10]
        items.append({
            "feed_id": f"event:{e['event_id']}",
            "item_type": "EVENT",
            "timestamp": observed_date,
            "event_date": event_date or None,
            "generated_at": str(e.get("first_observed_at") or ""),
            "severity": "INFO",
            "domain": "CORPORATE_BOND",
            "signal_type": None,
            "title": {
                "REGISTRATION": "Đăng ký giao dịch (Registration)",
                "DELISTING": "Hủy đăng ký giao dịch (Delisting)",
                "TRADING_SUSPENSION": "Tạm ngừng giao dịch (Trading Suspension)",
                "RATING_OBSERVATION": "Cập nhật xếp hạng tín nhiệm (Rating Observation)",
                "EARLY_REDEMPTION": "Mua lại trước hạn (Early Redemption)",
            }.get(str(e.get("event_type") or ""), str(e.get("event_type") or "Sự kiện TPDN").replace("_", " ").title()),
            "entity_id": e.get("bond_id") or e.get("issuer_id"),
            "source": e.get("source"),
            "status": None,
            "signal_id": None,
            "event_id": e["event_id"],
        })

    items.sort(
        key=lambda x: (
            x.get("timestamp") or "",
            x.get("generated_at") or "",
            SEVERITY_RANK.get(x.get("severity", "INFO"), 0),
        ),
        reverse=True,
    )
    return items[:limit]


@dataclass
class InvestigationCase:
    signal: dict
    evidence: dict
    related_observations: list[dict]
    historical_context: dict
    data_quality: dict
    possible_risk_transmission: list[str]
    monitor_next: list[str]


def _latest_related(rows: list[dict], domain: str, limit: int = 30) -> list[dict]:
    prefixes = RELATED_PREFIXES.get(domain, ())
    filtered = [
        r for r in rows
        if any(str(r.get("metric_id") or "").startswith(p) for p in prefixes)
    ]
    chosen: dict[tuple, dict] = {}
    for r in filtered:
        key = (r.get("metric_id"), r.get("entity_id"), r.get("source"))
        stamp = (str(r.get("period_end") or ""), str(r.get("fetched_at") or ""))
        old = chosen.get(key)
        old_stamp = (
            (str(old.get("period_end") or ""), str(old.get("fetched_at") or ""))
            if old else None
        )
        if old is None or stamp > old_stamp:
            chosen[key] = r

    def prefix_rank(row: dict) -> int:
        metric = str(row.get("metric_id") or "")
        for idx, prefix in enumerate(prefixes):
            if metric.startswith(prefix):
                return idx
        return len(prefixes)

    out = list(chosen.values())
    # Stable two-step sort: newest within each source family, preferred source family first.
    out.sort(
        key=lambda r: (str(r.get("period_end") or ""), str(r.get("fetched_at") or "")),
        reverse=True,
    )
    out.sort(key=prefix_rank)
    return out[:limit]


def _latest_by_period(rows: list[dict]) -> dict[str, dict]:
    chosen: dict[str, dict] = {}
    for row in rows:
        period = str(row.get("period_end") or "")
        if not period:
            continue
        old = chosen.get(period)
        if old is None or str(row.get("fetched_at") or "") > str(old.get("fetched_at") or ""):
            chosen[period] = row
    return chosen


def _curve_history(store, *, start_date: str, end_date: str) -> dict[str, Any]:
    five = store.observations_between(
        metric_id="HNX.GOV.TENOR_YIELD",
        entity_id="GOV_TENOR:5Y",
        start_date=start_date,
        end_date=end_date,
        source=None,
    )
    ten = store.observations_between(
        metric_id="HNX.GOV.TENOR_YIELD",
        entity_id="GOV_TENOR:10Y",
        start_date=start_date,
        end_date=end_date,
        source=None,
    )
    by5 = _latest_by_period(five)
    by10 = _latest_by_period(ten)
    periods = sorted(set(by5).intersection(by10))
    values = [
        (float(by10[d]["value"]) - float(by5[d]["value"])) * 100.0
        for d in periods
        if by5[d].get("value") is not None and by10[d].get("value") is not None
    ]
    hist: dict[str, Any] = {
        "metric_id": "HNX.GOV.CURVE_SLOPE_5Y10Y",
        "entity_id": "GOV_CURVE:5Y10Y",
        "unit": "bp",
        "count": len(values),
        "window_start": start_date,
        "window_end": end_date,
    }
    if values:
        hist.update({
            "min": min(values),
            "max": max(values),
            "latest": values[-1],
            "first": values[0],
        })
    return hist


def _primary_metric(signal: dict, evidence: dict) -> tuple[str | None, str | None]:
    typ = str(signal.get("signal_type") or "")
    if evidence.get("metric"):
        return str(evidence["metric"]), signal.get("entity_id")
    if evidence.get("metric_id"):
        return str(evidence["metric_id"]), signal.get("entity_id")
    if typ in {"YIELD_MOVE_HIGH", "CURVE_STEEPENING", "CURVE_FLATTENING"}:
        return "HNX.GOV.TENOR_YIELD", signal.get("entity_id") if typ == "YIELD_MOVE_HIGH" else None
    if typ.startswith("FX_"):
        return "VIRA.FX.INTERBANK", "INTERBANK"
    return None, None


def build_investigation_case(store, signal_id: str) -> InvestigationCase:
    signal = store.get_signal(signal_id)
    if not signal:
        raise KeyError(f"Signal not found: {signal_id}")
    evidence = _json(signal.get("evidence_json"))
    domain = str(signal.get("domain") or "OTHER")

    related = _latest_related(store.recent_observations(limit=2000), domain)
    quality_flags = sorted({str(r.get("quality_flag")) for r in related if r.get("quality_flag")})
    questionable = [r for r in related if str(r.get("quality_flag")) in {"C", "D", "X"}]
    data_quality = {
        "flags_present": quality_flags,
        "questionable_count": len(questionable),
        "status": "REVIEW" if any(f in {"D", "X"} for f in quality_flags) else ("CAUTION" if "C" in quality_flags else "OK"),
        "note": "Trạng thái DQ phản ánh các quan sát thị trường công khai liên quan; không dùng để xác nhận exposure nội bộ mô phỏng.",
    }

    metric, entity = _primary_metric(signal, evidence)
    hist: dict[str, Any] = {"metric_id": metric, "entity_id": entity, "count": 0}
    end = evidence.get("current_period") or evidence.get("period_end")
    if end:
        try:
            end_date = date.fromisoformat(str(end)[:10])
            start_date = end_date - timedelta(days=60)
            typ = str(signal.get("signal_type") or "")
            if typ in {"CURVE_STEEPENING", "CURVE_FLATTENING"}:
                hist = _curve_history(
                    store,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
            elif metric:
                rows = store.observations_between(
                    metric_id=metric,
                    entity_id=entity,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    source=None,
                )
                values = [float(r["value"]) for r in rows if r.get("value") is not None]
                if values:
                    hist.update({
                        "count": len(values),
                        "min": min(values),
                        "max": max(values),
                        "latest": values[-1],
                        "first": values[0],
                        "window_start": start_date.isoformat(),
                        "window_end": end_date.isoformat(),
                        "unit": rows[-1].get("unit"),
                    })
        except Exception:
            pass

    return InvestigationCase(
        signal=dict(signal), evidence=evidence, related_observations=related,
        historical_context=hist, data_quality=data_quality,
        possible_risk_transmission=TRANSMISSION.get(domain, ["No deterministic transmission narrative configured for this domain."]),
        monitor_next=MONITOR_NEXT.get(domain, ["Monitor subsequent public observations and source quality."]),
    )
