from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from src.common.numbers import parse_vn_number, parse_percent

OMO_URL = (
    "https://sbv.gov.vn/vi/nghi%E1%BB%87p-v%E1%BB%A5-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-m%E1%BB%9F"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
PARSER_VERSION = "sbv_omo_v1"


class SourceBlocked(RuntimeError):
    pass


class SourceSchemaChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class OmoRow:
    session_date: date
    deal_type: str
    tenor_days: int
    members_bid: int | None
    members_won: int | None
    volume_bn_vnd: float | None
    rate_pct: float | None
    maturity_date: date


def looks_blocked(html: str) -> bool:
    folded = (html or "").lower()
    return (
        "request rejected" in folded
        or "requested url was rejected" in folded
        or "support id" in folded and len(html) < 5000
    )


def _strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def _parse_session_date(text: str) -> date | None:
    m = re.search(
        r"Ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})",
        text or "",
        flags=re.I,
    )
    if not m:
        return None
    day, month, year = map(int, m.groups())
    return date(year, month, day)


def _parse_tenor_days(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(ngày|ngay|tuần|tuan|tháng|thang)", text or "", re.I)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    multiplier = {"ngày": 1, "ngay": 1, "tuần": 7, "tuan": 7, "tháng": 30, "thang": 30}[unit]
    return n * multiplier


def _parse_member_pair(value: str) -> tuple[int | None, int | None]:
    if "/" not in value:
        return None, None
    left, right = [x.strip() for x in value.split("/", 1)]
    a, b = parse_vn_number(left), parse_vn_number(right)
    return (int(a) if a is not None else None, int(b) if b is not None else None)


def parse_omo_html(html: str) -> list[OmoRow]:
    if looks_blocked(html):
        raise SourceBlocked("SBV returned a WAF/rejection page")

    date_match = re.search(r'ls01-date[^>]*>(.*?)</', html, re.S | re.I)
    session_date = _parse_session_date(_strip_tags(date_match.group(1)) if date_match else "")
    if session_date is None:
        raise SourceSchemaChanged("Cannot parse OMO session date (.ls01-date)")

    table_match = re.search(r'<table[^>]*class=["\'][^"\']*ls01-table[^"\']*["\'][^>]*>.*?</table>', html, re.S | re.I)
    if not table_match:
        raise SourceSchemaChanged("Cannot find OMO table (.ls01-table)")

    rows: list[OmoRow] = []
    deal_type: str | None = None
    for tr in re.findall(r"<tr\b.*?</tr>", table_match.group(0), re.S | re.I):
        cells = [_strip_tags(x) for x in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if not cells:
            continue

        if "ls01-group" in tr.lower() or (len(cells) == 1 and cells[0]):
            deal_type = cells[0]
            continue

        if len(cells) < 4 or cells[0].lower().startswith("tổng"):
            continue

        tenor_days = _parse_tenor_days(cells[0])
        if tenor_days is None:
            continue

        members_bid, members_won = _parse_member_pair(cells[1])
        volume = parse_vn_number(cells[2])
        rate = parse_percent(cells[3])
        rows.append(
            OmoRow(
                session_date=session_date,
                deal_type=deal_type or "UNKNOWN",
                tenor_days=tenor_days,
                members_bid=members_bid,
                members_won=members_won,
                volume_bn_vnd=volume,
                rate_pct=rate,
                maturity_date=session_date + timedelta(days=tenor_days),
            )
        )

    if not rows:
        raise SourceSchemaChanged("OMO table found but no data rows were parsed")
    return rows


def fetch_omo_html(timeout: int = 45) -> tuple[str, datetime]:
    response = requests.get(OMO_URL, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    fetched_at = datetime.now(timezone.utc)
    if looks_blocked(response.text):
        raise SourceBlocked("SBV returned a WAF/rejection page")
    return response.text, fetched_at


def archive_raw(html: str, session_date: date, root: Path) -> tuple[Path, str]:
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    folder = root / "sbv_omo" / session_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.html"
    if not path.exists():
        path.write_text(html, encoding="utf-8")
    return path, digest
