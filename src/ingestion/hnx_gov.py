from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

import requests

from src.common.http import resilient_session

BASE = "https://www.hnx.vn"
SECONDARY_ENDPOINT = f"{BASE}/ModuleReportBonds/Bond_KQGD_TrongNgay/GetTradingOutRightInDay"
AUCTION_ENDPOINT = f"{BASE}/ModuleReportBonds/Bond_DauThau/Bond_KetQua_DauThau"
SECONDARY_PAGE = f"{BASE}/vi-vn/trai-phieu/ket-qua-gd-trong-ngay.html?site=in"
AUCTION_PAGE = f"{BASE}/vi-vn/trai-phieu/ket-qua-dau-thau.html"
PARSER_VERSION = "hnx-gov-0.1.1"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
}
_TAG = re.compile(r"<[^>]+>")


class HnxSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SecondaryTrade:
    trade_date: date
    bond_code: str
    remaining_tenor_raw: str | None
    currency: str | None
    price: float | None
    ytm_pct: float | None
    volume: float | None
    trade_value_vnd: float | None
    investor_type: str | None


@dataclass(frozen=True)
class AuctionResult:
    auction_date: date
    auction_round: str | None
    bond_code: str
    issue_type: str | None
    tenor_raw: str | None
    offered_value_vnd: float | None
    bid_value_vnd: float | None
    awarded_value_vnd: float | None
    auction_yield_pct: float | None
    additional_offered_value_vnd: float | None = None
    additional_bid_value_vnd: float | None = None
    additional_awarded_value_vnd: float | None = None
    nominal_coupon_pct: float | None = None
    registered_yield_low_pct: float | None = None
    registered_yield_high_pct: float | None = None


def _norm(text: str | None) -> str:
    if text is None:
        return ""
    s = html_lib.unescape(str(text)).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    repl = str.maketrans("áàảãạăắằẳẵặâấầẩẫậđéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ", "aaaaaaaaaaaaaaaaadeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyy")
    return s.translate(repl)


def parse_hnx_number(value: str | None) -> float | None:
    """Parse HNX numeric strings across old/new formats.

    Examples: 1.234.567 -> 1234567; 4,0003 -> 4.0003; 2.35 -> 2.35.
    """
    if value is None:
        return None
    s = str(value).strip().replace("%", "").replace("\xa0", "")
    if not s or s in {"-", "–", "—"}:
        return None
    s = re.sub(r"[^0-9,\.\-+]", "", s)
    if not s:
        return None
    if "," in s:
        # Vietnamese convention: dots are grouping, comma is decimal.
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") >= 2:
        s = s.replace(".", "")
    elif s.count(".") == 1:
        left, right = s.split(".")
        # One dot with a 3-digit RHS is usually grouping on HNX unless the LHS is 1-2 digits
        # and the value is rate/price-like. Keep decimals such as 2.35; group 1.000.
        if len(right) == 3 and len(left.lstrip("+-")) >= 1:
            s = left + right
    try:
        return float(s)
    except ValueError:
        return None


def tenor_years(value: str | None) -> float | None:
    if not value:
        return None
    s = _norm(value)
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(nam|thang|year|month|y|m)\b", s)
    if not m:
        # HNX sometimes exposes remaining tenor as number of days.
        d = re.search(r"(\d+)\s*ngay", s)
        return float(d.group(1)) / 365.25 if d else None
    v = float(m.group(1).replace(",", "."))
    return v / 12.0 if m.group(2) in {"thang", "month", "m"} else v


def canonical_tenor(value: str | None) -> str | None:
    years = tenor_years(value)
    if years is None:
        return None
    buckets = [1, 2, 3, 5, 7, 10, 15, 20, 30]
    nearest = min(buckets, key=lambda x: abs(x - years))
    # Avoid forcing a wildly different maturity into a benchmark bucket.
    tolerance = max(0.75, nearest * 0.18)
    return f"{nearest}Y" if abs(nearest - years) <= tolerance else None


def _cells(row_html: str) -> list[str]:
    out: list[str] = []
    for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, re.S | re.I):
        t = html_lib.unescape(_TAG.sub("", c)).replace("\xa0", " ")
        out.append(" ".join(t.split()))
    return out


def parse_table(html: str) -> tuple[list[str], list[list[str]]]:
    m = re.search(r'<table id=["\']_tableDatas["\'].*?</table>', html, re.S | re.I)
    if not m:
        raise HnxSourceError("HNX response did not contain table#_tableDatas")
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", m.group(0), re.S | re.I)
    if not rows:
        return [], []
    header = _cells(rows[0])
    body = []
    for row in rows[1:]:
        c = _cells(row)
        if c and any(c):
            body.append(c)
    return header, body


def _header_index(header: Iterable[str], aliases: Iterable[str]) -> int | None:
    h = [_norm(x) for x in header]
    a = [_norm(x) for x in aliases]
    for i, col in enumerate(h):
        if any(alias == col or alias in col for alias in a):
            return i
    return None


def _get(row: list[str], idx: int | None) -> str | None:
    return row[idx].strip() if idx is not None and idx < len(row) and row[idx].strip() else None


def parse_secondary_html(html: str, trade_date: date) -> list[SecondaryTrade]:
    head, rows = parse_table(html)
    idx = {
        "bond": _header_index(head, ["ma tp", "ma trai phieu"]),
        "tenor": _header_index(head, ["ky han con lai", "ky han"]),
        "currency": _header_index(head, ["tien te", "loai tien te"]),
        "price": _header_index(head, ["gia yet", "gia", "gia thuc hien"]),
        "ytm": _header_index(head, ["loi suat dao han", "ytm", "loi suat"]),
        "volume": _header_index(head, ["khoi luong", "klgd", "kl"]),
        "value": _header_index(head, ["gia tri giao dich", "gtgd", "gia tri gd"]),
        "investor": _header_index(head, ["loai ndt", "nha dau tu", "doi tuong"]),
    }
    if idx["bond"] is None or idx["ytm"] is None:
        raise HnxSourceError(f"Unexpected secondary-market columns: {head}")
    out: list[SecondaryTrade] = []
    for r in rows:
        bond = _get(r, idx["bond"])
        if not bond:
            continue
        out.append(SecondaryTrade(
            trade_date=trade_date,
            bond_code=bond,
            remaining_tenor_raw=_get(r, idx["tenor"]),
            currency=_get(r, idx["currency"]),
            price=parse_hnx_number(_get(r, idx["price"])),
            ytm_pct=parse_hnx_number(_get(r, idx["ytm"])),
            volume=parse_hnx_number(_get(r, idx["volume"])),
            trade_value_vnd=parse_hnx_number(_get(r, idx["value"])),
            investor_type=_get(r, idx["investor"]),
        ))
    return out


def _parse_date(value: str | None) -> date | None:
    """Parse an HNX date even when it is embedded in a longer label."""
    if not value:
        return None
    text = str(value).strip()
    candidates = [text]
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", text)
    if m and m.group(1) != text:
        candidates.append(m.group(1))
    for candidate in candidates:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def parse_auction_html(html: str) -> list[AuctionResult]:
    head, rows = parse_table(html)
    idx = {
        # HNX current schema (Sep-2026) labels the auction/organisation date
        # as "Ngày TCPH" (ngày tổ chức phát hành), while older responses used
        # "Ngày đấu thầu". "Ngày phát hành" is a different field and must
        # not be silently substituted for the auction date.
        "date": _header_index(head, ["ngay dau thau", "ngay tcph", "ngay to chuc phat hanh"]),
        "round": _header_index(head, ["dot dau thau", "dot"]),
        "bond": _header_index(head, ["ma trai phieu", "ma tp"]),
        "issue_type": _header_index(head, ["phuong thuc phat hanh", "kieu phat hanh"]),
        "tenor": _header_index(head, ["ky han"]),
        "offered": _header_index(head, ["gt goi thau", "gia tri goi thau", "chao thau"]),
        "bid": _header_index(head, ["gt dat thau", "gia tri dat thau", "du thau"]),
        "awarded": _header_index(head, ["gt trung thau", "gia tri trung thau", "kl trung thau"]),
        "add_offered": _header_index(head, ["gt goi thau phat hanh them"]),
        "add_bid": _header_index(head, ["gt dat thau phat hanh them"]),
        "add_awarded": _header_index(head, ["gt trung thau phat hanh them"]),
        "coupon": _header_index(head, ["lai suat danh nghia"]),
        "yield": _header_index(head, ["lai suat trung thau", "loi suat trung thau"]),
        "yield_low": _header_index(head, ["ls dang ky thap nhat", "lai suat dang ky thap nhat"]),
        "yield_high": _header_index(head, ["ls dang ky cao nhat", "lai suat dang ky cao nhat"]),
    }
    if idx["date"] is None or idx["bond"] is None:
        raise HnxSourceError(f"Unexpected auction columns: {head}")
    out: list[AuctionResult] = []
    for r in rows:
        d = _parse_date(_get(r, idx["date"]))
        bond = _get(r, idx["bond"])
        if not d or not bond:
            continue
        out.append(AuctionResult(
            auction_date=d,
            auction_round=_get(r, idx["round"]),
            bond_code=bond,
            issue_type=_get(r, idx["issue_type"]),
            tenor_raw=_get(r, idx["tenor"]),
            offered_value_vnd=parse_hnx_number(_get(r, idx["offered"])),
            bid_value_vnd=parse_hnx_number(_get(r, idx["bid"])),
            awarded_value_vnd=parse_hnx_number(_get(r, idx["awarded"])),
            auction_yield_pct=parse_hnx_number(_get(r, idx["yield"])),
            additional_offered_value_vnd=parse_hnx_number(_get(r, idx["add_offered"])),
            additional_bid_value_vnd=parse_hnx_number(_get(r, idx["add_bid"])),
            additional_awarded_value_vnd=parse_hnx_number(_get(r, idx["add_awarded"])),
            nominal_coupon_pct=parse_hnx_number(_get(r, idx["coupon"])),
            registered_yield_low_pct=parse_hnx_number(_get(r, idx["yield_low"])),
            registered_yield_high_pct=parse_hnx_number(_get(r, idx["yield_high"])),
        ))
    return out


def _session(reference_url: str) -> requests.Session:
    # Use the OS trust store when available. This fixes a common Windows case where
    # browsers can build the HNX certificate chain but Requests/certifi cannot.
    s = resilient_session(user_agent=_HEADERS["User-Agent"], retries=2)
    try:
        s.get(reference_url, timeout=(12, 30))
    except requests.RequestException:
        # Some HNX front pages are occasionally unavailable while the report endpoint still works.
        pass
    return s


def fetch_secondary_day(d: date) -> tuple[str, datetime]:
    s = _session(SECONDARY_PAGE)
    ds = d.strftime("%d/%m/%Y")
    r = s.post(SECONDARY_ENDPOINT, timeout=(15, 60), data={
        "p_keysearch": f"{ds}|",
        "pColOrder": "col_c", "pOrderType": "ASC",
        "pCurrentPage": 1, "pRecordOnPage": 1000,
        "pIsSearch": 1, "pIsChangeTab": 0,
    })
    r.raise_for_status()
    if "requested url was rejected" in r.text.lower():
        raise HnxSourceError("HNX blocked the secondary-market request")
    return r.text, datetime.now(timezone.utc)


def fetch_auctions(start: date, end: date) -> tuple[str, datetime]:
    s = _session(AUCTION_PAGE)
    key = f"{start:%d/%m/%Y}|{end:%d/%m/%Y}|0||3|'VND'|0|0"
    r = s.post(AUCTION_ENDPOINT, timeout=(15, 90), data={
        "p_keysearch": key,
        "pColOrder": "col_x", "pOrderType": "DESC",
        "pCurrentPage": 1, "pRecordOnPage": 5000,
        "pIsSearch": 1,
    })
    r.raise_for_status()
    if "requested url was rejected" in r.text.lower():
        raise HnxSourceError("HNX blocked the auction request")
    return r.text, datetime.now(timezone.utc)
