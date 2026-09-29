from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.common.numbers import parse_percent, parse_vn_number
from src.ingestion.vira import PARSER_VERSION, ViraArticle


@dataclass(frozen=True)
class ExtractedMetric:
    metric_id: str
    entity_type: str
    entity_id: str
    value: float
    unit: str
    measure_type: str
    semantic_group: str


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _section(text: str, start: str, stops: list[str]) -> str:
    start_m = re.search(start, text, flags=re.IGNORECASE | re.UNICODE)
    if not start_m:
        return ""
    tail = text[start_m.start():]
    stop_positions: list[int] = []
    for stop in stops:
        m = re.search(stop, tail[start_m.end() - start_m.start():], flags=re.IGNORECASE | re.UNICODE)
        if m:
            stop_positions.append((start_m.end() - start_m.start()) + m.start())
    end = min(stop_positions) if stop_positions else len(tail)
    return tail[:end]


def _extract_fx(text: str) -> list[ExtractedMetric]:
    sec = _section(text, r"Thị trường ngoại tệ:", [r"Thị trường tiền tệ LNH:", r"Thị trường mở:", r"Nghiệp vụ thị trường mở:"])
    if not sec:
        return []

    def one(pattern: str):
        m = re.search(pattern, sec, flags=re.IGNORECASE | re.UNICODE | re.DOTALL)
        return parse_vn_number(m.group(1)) if m else None

    def two(pattern: str):
        m = re.search(pattern, sec, flags=re.IGNORECASE | re.UNICODE | re.DOTALL)
        if not m:
            return None, None
        return parse_vn_number(m.group(1)), parse_vn_number(m.group(2))

    vals = {
        "VIRA.FX.CENTRAL": one(r"tỷ giá trung tâm.*?mức\s+([\d\.,]+)\s*VND/USD"),
        "VIRA.FX.SBV_BUY": one(r"tỷ giá mua giao ngay.*?mức\s+([\d\.,]+)\s*VND/USD"),
        "VIRA.FX.SBV_SELL": one(r"tỷ giá bán giao ngay.*?mức\s+([\d\.,]+)\s*VND/USD"),
        "VIRA.FX.INTERBANK": one(r"(?:tỷ giá LNH|Trên thị trường LNH).*?(?:tại|mức)\s+([\d\.,]+)\s*VND/USD"),
    }
    free_buy, free_sell = two(r"(?:thị trường tự do).*?(?:giao dịch tại|giao dịch ở mức)\s+([\d\.,]+)\s*VND/USD\s+và\s+([\d\.,]+)\s*VND/USD")
    vals["VIRA.FX.FREE_BUY"] = free_buy
    vals["VIRA.FX.FREE_SELL"] = free_sell

    out = []
    for metric, value in vals.items():
        if value is not None:
            out.append(ExtractedMetric(metric, "FX_MARKET", metric.split(".")[-1], float(value), "VND_per_USD", "SNAPSHOT", "FX"))
    return out


def _tenor_pairs(segment: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for tenor, raw in re.findall(r"\b(ON|1W|2W|3W|1M|2M|3M|6M|9M|12M)\s+([\d\.,]+)\s*%?", segment, flags=re.IGNORECASE):
        value = parse_percent(raw)
        if value is not None:
            out[tenor.upper()] = float(value)
    return out


def _extract_ibor(text: str) -> list[ExtractedMetric]:
    sec = _section(text, r"Thị trường tiền tệ LNH:", [r"Thị trường mở:", r"Nghiệp vụ thị trường mở:", r"Thị trường trái phiếu:", r"Thị trường chứng khoán:"])
    if not sec:
        return []
    # Split VND and USD at the explicit USD sentence if present.
    usd_m = re.search(r"Lãi suất(?:\s+bình quân)?\s+LNH\s+USD|Lãi suất\s+USD\s+LNH", sec, flags=re.IGNORECASE | re.UNICODE)
    if usd_m:
        vnd_seg, usd_seg = sec[:usd_m.start()], sec[usd_m.start():]
    else:
        vnd_seg, usd_seg = sec, ""
    vnd = _tenor_pairs(vnd_seg)
    usd = _tenor_pairs(usd_seg)
    out: list[ExtractedMetric] = []
    for ccy, vals in (("VND", vnd), ("USD", usd)):
        for tenor, value in vals.items():
            out.append(ExtractedMetric("VIRA.IBOR.RATE", "IBOR_TENOR", f"IBOR:{ccy}:{tenor}", value, "pct", "SNAPSHOT", "IBOR"))
    return out


def _extract_gov_yields(text: str) -> list[ExtractedMetric]:
    # Daily wording may not include the 'Thị trường trái phiếu:' heading.
    m = re.search(
        r"Lợi suất\s+TPCP.*?(?:chốt(?:\s+phiên)?|giao dịch quanh)\s*:?\s*(.*?)(?:Nghiệp vụ thị trường mở:|Thị trường mở:|Thị trường chứng khoán:|$)",
        text,
        flags=re.IGNORECASE | re.UNICODE | re.DOTALL,
    )
    if not m:
        return []
    seg = m.group(1)
    out: list[ExtractedMetric] = []
    for tenor, raw in re.findall(r"\b(1Y|2Y|3Y|5Y|7Y|10Y|15Y|20Y|30Y)\s+([\d\.,]+)\s*%", seg, flags=re.IGNORECASE):
        value = parse_percent(raw)
        if value is not None:
            out.append(ExtractedMetric("VIRA.GOV.YIELD", "GOV_TENOR", f"GOV_TENOR:{tenor.upper()}", float(value), "pct", "SNAPSHOT", "GOV"))
    return out


def _extract_omo(text: str) -> list[ExtractedMetric]:
    sec = _section(text, r"(?:Nghiệp vụ thị trường mở|Thị trường mở):", [r"Thị trường trái phiếu:", r"Thị trường chứng khoán:", r"Tin quốc tế"])
    if not sec:
        return []

    def num(pattern: str, *, signed_direction: bool = False):
        m = re.search(pattern, sec, flags=re.IGNORECASE | re.UNICODE | re.DOTALL)
        if not m:
            return None
        if signed_direction:
            direction, raw = m.groups()
            value = parse_vn_number(raw)
            if value is None:
                return None
            return value if direction.lower().startswith("bơm") else -value
        return parse_vn_number(m.group(1))

    tender = num(r"(?:chào thầu|gọi thầu)\s+([\d\.,]+)\s*tỷ\s+đồng")
    # Daily VIRA sometimes states an amount "at each tenor"; convert it to the
    # session total only when the tenor count is explicit in the same sentence.
    each_m = re.search(
        r"(?:chào thầu|gọi thầu)\s+([\d\.,]+)\s*tỷ\s+đồng\s+ở\s+mỗi\s+kỳ\s+hạn\s+([^\.]+)",
        sec, flags=re.IGNORECASE | re.UNICODE,
    )
    if each_m:
        per_tenor = parse_vn_number(each_m.group(1))
        tenor_count = len(re.findall(r"\b\d+\s*(?:ngày|day|D)\b", each_m.group(2), flags=re.IGNORECASE))
        if per_tenor is not None and tenor_count > 0:
            tender = per_tenor * tenor_count
    win = num(r"(?:Có|Kết quả có)\s+([\d\.,]+)\s*tỷ\s+đồng\s+trúng thầu")
    maturity = num(r"(?:Có|Trong tuần có)\s+([\d\.,]+)\s*tỷ\s+đồng\s+(?:đáo hạn|đến hạn)")
    net = num(r"NHNN\s+(bơm|hút)\s+ròng\s+([\d\.,]+)\s*tỷ\s+đồng", signed_direction=True)
    outstanding = num(r"Có\s+([\d\.,]+)\s*tỷ\s+đồng\s+lưu hành\s+trên\s+kênh\s+cầm cố")
    rate = None
    rate_m = re.search(r"lãi suất.*?mức\s+([\d\.,]+)\s*%", sec, flags=re.IGNORECASE | re.UNICODE | re.DOTALL)
    if rate_m:
        rate = parse_percent(rate_m.group(1))

    specs = [
        ("VIRA.OMO.REPO.TENDER", tender, "VND_bn", "FLOW"),
        ("VIRA.OMO.REPO.WIN", win, "VND_bn", "FLOW"),
        ("VIRA.OMO.REPO.MATURITY", maturity, "VND_bn", "FLOW"),
        ("VIRA.OMO.REPO.NET", net, "VND_bn", "FLOW"),
        ("VIRA.OMO.REPO.OUTSTANDING", outstanding, "VND_bn", "STOCK"),
        ("VIRA.OMO.REPO.RATE", rate, "pct", "SNAPSHOT"),
    ]
    return [
        ExtractedMetric(metric, "OMO_REPO", "VIRA_OMO:REPO", float(value), unit, measure_type, "OMO")
        for metric, value, unit, measure_type in specs if value is not None
    ]


def extract_metrics(article: ViraArticle) -> list[ExtractedMetric]:
    return _extract_fx(article.text) + _extract_ibor(article.text) + _extract_gov_yields(article.text) + _extract_omo(article.text)


def article_to_observations(
    article: ViraArticle,
    *,
    fetched_at: datetime,
    raw_path: str,
    raw_hash: str,
) -> list[dict]:
    processed = datetime.now(timezone.utc)
    metrics = extract_metrics(article)
    out: list[dict] = []

    daily_date_fallback = article.article_type == "DAILY" and article.market_date_inferred

    for item in metrics:
        if article.article_type == "DAILY":
            assert article.market_date is not None
            period_start = period_end = article.market_date
            frequency = "DAILY"
            observation_method = "DIRECT_DAILY"
        else:
            assert article.week_start is not None and article.week_end is not None
            if item.semantic_group == "OMO" and item.measure_type == "FLOW":
                period_start, period_end = article.week_start, article.week_end
                frequency = "WEEKLY"
                observation_method = "WEEKLY_AGGREGATE"
            else:
                # FX/IBOR/GOV and OMO stock/rate are end-of-week states, not weekly sums.
                period_start = period_end = article.week_end
                frequency = "WEEKLY_EOP"
                observation_method = "DIRECT_WEEKLY_EOP"

        quality = "C"  # VIRA is a secondary/cross-check source in Project 2.
        if daily_date_fallback or article.publication_time_inferred:
            quality = "D"

        dims = {
            "article_type": article.article_type,
            "article_title": article.title,
            "semantic_group": item.semantic_group,
            "week_start": article.week_start.isoformat() if article.week_start else None,
            "week_end": article.week_end.isoformat() if article.week_end else None,
            "market_date_fallback": daily_date_fallback,
            "publication_time_inferred": article.publication_time_inferred,
        }
        payload = {
            "metric_id": item.metric_id,
            "entity_id": item.entity_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "value": item.value,
            "unit": item.unit,
            "measure_type": item.measure_type,
            "frequency": frequency,
            "method": observation_method,
        }
        record_hash = _hash(payload)
        out.append({
            "observation_id": str(uuid.uuid5(uuid.NAMESPACE_URL, record_hash)),
            "metric_id": item.metric_id,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "value": item.value,
            "unit": item.unit,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "as_of_time": None,
            "measure_type": item.measure_type,
            "frequency": frequency,
            "source": "VIRA",
            "source_url": article.url,
            "source_published_at": article.article_date.isoformat(),
            "first_observed_at": fetched_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "processed_at": processed.isoformat(),
            "observation_method": observation_method,
            "quality_flag": quality,
            "raw_object_id": raw_path,
            "parser_version": PARSER_VERSION,
            "record_hash": record_hash,
            "dims_json": json.dumps(dims, ensure_ascii=False, sort_keys=True),
        })
    return out
