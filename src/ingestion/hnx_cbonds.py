from __future__ import annotations

import hashlib
import html as html_lib
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

import requests

from src.common.http import resilient_session

BASE = "https://cbonds.hnx.vn"
BOND_LIST_URL = f"{BASE}/danh-muc-trai-phieu"
ISSUER_LIST_URL = f"{BASE}/to-chuc-phat-hanh/danh-sach-doanh-nghiep"
RATING_URL = f"{BASE}/danh-sach-thong-tin-xep-hang-tin-nhiem"
DISCLOSURE_URL = f"{BASE}/to-chuc-phat-hanh/tin-cong-bo"
TRADING_STATUS_URL = f"{BASE}/cbtt-dang-ky-giao-dich"
PARSER_VERSION = "hnx-cbonds-0.1.0"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
}
_TAG = re.compile(r"<[^>]+>")


class CbisSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class IssuerRecord:
    issuer_code: str | None
    issuer_name: str
    sector: str | None
    charter_capital_vnd: float | None
    rating_agency: str | None
    latest_rating: str | None
    rating_effective_date: date | None


@dataclass(frozen=True)
class BondRecord:
    disclosure_code: str
    trading_code: str | None
    isin: str | None
    issuer_name: str
    face_value_vnd: float | None
    registered_quantity: float | None
    registration_status: str | None
    first_trade_date: date | None
    last_trade_date: date | None
    investor_scope: str | None


@dataclass(frozen=True)
class RatingRecord:
    agency: str
    subject_type: str | None
    bond_code: str | None
    issuer_name: str
    rating: str
    effective_date: date | None
    rating_type: str | None


@dataclass(frozen=True)
class DisclosureRecord:
    published_date: date | None
    issuer_name: str
    bond_codes: tuple[str, ...]
    title: str
    category: str
    status: str | None
    source_url: str


@dataclass(frozen=True)
class TradingStatusRecord:
    title: str
    issuer_name: str
    disclosure_code: str | None
    trading_code: str | None
    reason: str | None
    status: str | None
    effective_date: date | None
    source_url: str


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = html_lib.unescape(str(s)).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return s


def normalize_issuer_name(name: str) -> str:
    s = _norm(name)
    s = re.sub(r"\b(cong ty|ctcp|tnhh|ngan hang|thuong mai co phan|tmcp|tap doan)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace("%", "").replace("\xa0", "")
    if not s or s in {"-", "–", "—"}:
        return None
    s = re.sub(r"[^0-9,\.\-+]", "", s)
    if not s:
        return None
    # CBIS commonly displays comma grouping (1,000,000) and sometimes Vietnamese decimals.
    if "," in s and "." not in s:
        groups = s.split(",")
        if len(groups) > 1 and all(len(g) == 3 for g in groups[1:]):
            s = "".join(groups)
        else:
            s = s.replace(",", ".")
    elif "," in s and "." in s:
        # Infer the final separator as decimal only if the trailing group is not 3 digits.
        if len(s.rsplit(",", 1)[1]) != 3:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") >= 2:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _cell_text(raw: str) -> str:
    return " ".join(html_lib.unescape(_TAG.sub("", raw)).replace("\xa0", " ").split())


def _tables(html: str) -> list[tuple[list[str], list[list[str]]]]:
    out = []
    for table in re.findall(r"<table\b[^>]*>(.*?)</table>", html, re.S | re.I):
        trs = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not trs:
            continue
        parsed = []
        for tr in trs:
            cells = [_cell_text(c) for c in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            if cells and any(cells):
                parsed.append(cells)
        if len(parsed) >= 2:
            out.append((parsed[0], parsed[1:]))
    return out


def _find_table(html: str, required_headers: Iterable[str]) -> tuple[list[str], list[list[str]]]:
    req = [_norm(x) for x in required_headers]
    for header, rows in _tables(html):
        nh = [_norm(x) for x in header]
        if all(any(r in h for h in nh) for r in req):
            return header, rows
    raise CbisSourceError(f"CBIS table not found for required headers: {list(required_headers)}")


def _idx(header: list[str], aliases: Iterable[str]) -> int | None:
    nh = [_norm(x) for x in header]
    for i, h in enumerate(nh):
        for a in aliases:
            na = _norm(a)
            if h == na or na in h:
                return i
    return None


def _get(row: list[str], idx: int | None) -> str | None:
    return row[idx].strip() if idx is not None and idx < len(row) and row[idx].strip() else None


def parse_issuer_list(html: str) -> list[IssuerRecord]:
    header, rows = _find_table(html, ["Tên doanh nghiệp", "Loại hình doanh nghiệp"])
    i_name = _idx(header, ["Tên doanh nghiệp"])
    i_sector = _idx(header, ["Lĩnh vực", "Ngành nghề"])
    i_capital = _idx(header, ["Vốn điều lệ"])
    i_agency = _idx(header, ["Đơn vị XHTN", "Tổ chức XHTN"])
    i_rating = _idx(header, ["Kết quả XHTN"])
    i_date = _idx(header, ["Ngày hiệu lực", "Hiệu lực XHTN"])
    out = []
    for r in rows:
        raw_name = _get(r, i_name)
        if not raw_name:
            continue
        m = re.match(r"\s*([A-Z0-9]+)\s*-\s*(.+)", raw_name)
        issuer_code = m.group(1) if m else None
        issuer_name = m.group(2).strip() if m else raw_name
        out.append(IssuerRecord(
            issuer_code=issuer_code,
            issuer_name=issuer_name,
            sector=_get(r, i_sector),
            charter_capital_vnd=parse_number(_get(r, i_capital)),
            rating_agency=_get(r, i_agency),
            latest_rating=_get(r, i_rating),
            rating_effective_date=parse_date(_get(r, i_date)),
        ))
    return out


def parse_bond_list(html: str) -> list[BondRecord]:
    header, rows = _find_table(html, ["Mã trái phiếu CBTT", "Mã trái phiếu giao dịch", "Mã ISIN"])
    i_disc = _idx(header, ["Mã trái phiếu CBTT"])
    i_trade = _idx(header, ["Mã trái phiếu giao dịch"])
    i_isin = _idx(header, ["Mã ISIN"])
    i_issuer = _idx(header, ["Tên tổ chức phát hành"])
    i_face = _idx(header, ["Mệnh giá"])
    i_qty = _idx(header, ["Khối lượng ĐKGD"])
    i_status = _idx(header, ["Trạng thái đăng ký giao dịch"])
    i_first = _idx(header, ["Ngày giao dịch đầu tiên"])
    i_last = _idx(header, ["Ngày giao dịch cuối cùng"])
    i_scope = _idx(header, ["Đối tượng giao dịch"])
    if i_disc is None or i_issuer is None:
        raise CbisSourceError(f"Unexpected CBIS bond-list columns: {header}")
    out = []
    for r in rows:
        code = _get(r, i_disc)
        issuer = _get(r, i_issuer)
        if not code or not issuer:
            continue
        out.append(BondRecord(
            disclosure_code=code,
            trading_code=_get(r, i_trade),
            isin=_get(r, i_isin),
            issuer_name=issuer,
            face_value_vnd=parse_number(_get(r, i_face)),
            registered_quantity=parse_number(_get(r, i_qty)),
            registration_status=_get(r, i_status),
            first_trade_date=parse_date(_get(r, i_first)),
            last_trade_date=parse_date(_get(r, i_last)),
            investor_scope=_get(r, i_scope),
        ))
    return out


def parse_ratings(html: str) -> list[RatingRecord]:
    header, rows = _find_table(html, ["Đơn vị XHTN", "Kết quả XHTN"])
    i_agency = _idx(header, ["Đơn vị XHTN"])
    i_subject = _idx(header, ["Đối tượng XHTN"])
    i_bond = _idx(header, ["Mã trái phiếu"])
    i_issuer = _idx(header, ["TCPH"])
    i_rating = _idx(header, ["Kết quả XHTN"])
    i_date = _idx(header, ["Hiệu lực XHTN từ ngày", "Ngày hiệu lực"])
    i_type = _idx(header, ["Loại xếp hạng"])
    out = []
    for r in rows:
        agency, issuer, rating = _get(r, i_agency), _get(r, i_issuer), _get(r, i_rating)
        if not agency or not issuer or not rating:
            continue
        out.append(RatingRecord(
            agency=agency,
            subject_type=_get(r, i_subject),
            bond_code=_get(r, i_bond),
            issuer_name=issuer,
            rating=rating,
            effective_date=parse_date(_get(r, i_date)),
            rating_type=_get(r, i_type),
        ))
    return out


def _bond_codes(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parts = re.split(r"[,;\n]+", value)
    return tuple(x.strip() for x in parts if x.strip())


def parse_disclosures(html: str, source_url: str = DISCLOSURE_URL) -> list[DisclosureRecord]:
    out: list[DisclosureRecord] = []
    for header, rows in _tables(html):
        i_date = _idx(header, ["Ngày đăng tin"])
        i_issuer = _idx(header, ["Tên doanh nghiệp"])
        i_bonds = _idx(header, ["Mã TP liên quan", "Mã trái phiếu liên quan"])
        i_title = _idx(header, ["Tiêu đề tin"])
        i_status = _idx(header, ["Tình trạng"])
        if i_date is None or i_issuer is None or i_title is None:
            continue
        # Infer disclosure section/category from header/content conservatively.
        joined = _norm(" ".join(header))
        for r in rows:
            title, issuer = _get(r, i_title), _get(r, i_issuer)
            if not title or not issuer:
                continue
            nt = _norm(title)
            if "cbtt bat thuong" in nt or any(k in nt for k in ["gia han", "thay doi dieu kien", "cham thanh toan", "tai san bao dam"]):
                category = "ABNORMAL"
            elif "bao cao" in nt:
                category = "PERIODIC"
            else:
                category = "OTHER"
            out.append(DisclosureRecord(
                published_date=parse_date(_get(r, i_date)),
                issuer_name=issuer,
                bond_codes=_bond_codes(_get(r, i_bonds)),
                title=title,
                category=category,
                status=_get(r, i_status),
                source_url=source_url,
            ))
    return out


def parse_trading_status(html: str, source_url: str = TRADING_STATUS_URL) -> list[TradingStatusRecord]:
    out = []
    for header, rows in _tables(html):
        i_title = _idx(header, ["Tiêu đề"])
        i_issuer = _idx(header, ["Tên tổ chức phát hành"])
        i_disc = _idx(header, ["Mã trái phiếu CBTT"])
        i_trade = _idx(header, ["Mã trái phiếu giao dịch"])
        i_reason = _idx(header, ["Lý do"])
        i_status = _idx(header, ["Tình trạng"])
        i_date = _idx(header, ["Ngày thực hiện", "Ngày thông báo ĐKGD"])
        if i_title is None or i_issuer is None:
            continue
        for r in rows:
            title, issuer = _get(r, i_title), _get(r, i_issuer)
            if not title or not issuer:
                continue
            out.append(TradingStatusRecord(
                title=title,
                issuer_name=issuer,
                disclosure_code=_get(r, i_disc),
                trading_code=_get(r, i_trade),
                reason=_get(r, i_reason),
                status=_get(r, i_status),
                effective_date=parse_date(_get(r, i_date)),
                source_url=source_url,
            ))
    return out


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_page(url: str) -> tuple[str, datetime]:
    # CBIS can be slow/intermittent from residential networks. Reuse browser-like
    # headers, OS TLS trust and short connect retries; never disable certificate checks.
    s = resilient_session(user_agent=_HEADERS["User-Agent"], retries=2)
    if os.getenv("FRS_HNX_TLS_COMPAT", "0") == "1":
        s.verify = False
    s.headers.update({"Referer": f"{BASE}/", "Origin": BASE})
    try:
        # Warm the host first so cookies/session state are available to detail pages.
        if url != f"{BASE}/":
            try:
                s.get(f"{BASE}/", timeout=(10, 30), allow_redirects=True)
            except requests.RequestException:
                pass
        r = s.get(url, timeout=(12, 60), allow_redirects=True)
        r.raise_for_status()
    except requests.ConnectTimeout as exc:
        raise CbisSourceError(
            "CBIS connection timed out. The source is reachable publicly, but this local network/request path did not respond; retry later or test from GitHub Actions/cloud."
        ) from exc
    except requests.exceptions.SSLError as exc:
        raise CbisSourceError(
            "CBIS TLS verification failed even after trying the operating-system trust store."
        ) from exc
    text = r.text
    low = text.lower()
    if "requested url was rejected" in low or "access denied" in low:
        raise CbisSourceError("CBIS blocked the automated request")
    return text, datetime.now(timezone.utc)
