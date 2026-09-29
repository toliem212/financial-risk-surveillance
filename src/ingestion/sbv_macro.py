from __future__ import annotations

import calendar
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup

from src.common.numbers import parse_vn_number, parse_percent

BASE = "https://sbv.gov.vn/vi/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
PARSER_VERSION = "sbv_macro_v1"
REJECT_MARKERS = ("request rejected", "requested url was rejected", "support id")

PAGES = {
    "m2": "tong-phuong-tien-thanh-toan",
    "credit": "du-no-tin-dung-doi-voi-nen-kt-dttktt",
    "ldr": "ty-le-du-no-cho-vay-so-voi-tong-tien-gui",
}


class SourceBlocked(RuntimeError):
    pass


class SourceSchemaChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class MacroRow:
    page_id: str
    label: str
    reference_month: date
    level: float | None
    growth_ytd_pct: float | None


def _fold(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def _looks_blocked(html: str) -> bool:
    folded = (html or "").lower()
    return any(m in folded for m in REJECT_MARKERS) and len(html or "") < 10000


def _reference_month(text: str) -> date | None:
    m = re.search(r"thang\s*(\d{1,2})\s*nam\s*(\d{4})", _fold(text))
    if not m:
        return None
    month, year = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return date(year, month, 1)


def _first_non_numeric(cells: list[str]) -> str:
    for cell in cells:
        clean = cell.strip(" -–—")
        if not clean:
            continue
        # STT and pure numbers are not labels.
        if parse_vn_number(clean) is None:
            return clean
    return ""


def _row_numbers(cells: list[str], label: str) -> list[float]:
    out: list[float] = []
    seen_label = False
    for cell in cells:
        if not seen_label:
            if cell.strip(" -–—") == label:
                seen_label = True
            continue
        v = parse_vn_number(cell)
        if v is not None:
            out.append(v)
    return out


def parse_page(html: str, *, page_id: str) -> list[MacroRow]:
    if _looks_blocked(html):
        raise SourceBlocked(f"SBV macro page blocked: {page_id}")

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    page_text = soup.get_text(" ", strip=True)
    page_period = _reference_month(page_text)

    rows_out: list[MacroRow] = []
    seen: set[tuple] = set()
    for table in soup.find_all("table"):
        rows = [
            [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in tr.find_all(["td", "th"])]
            for tr in table.find_all("tr")
        ]
        rows = [r for r in rows if any(r)]
        if len(rows) < 2:
            continue

        header_idx = None
        level_idx = None
        growth_idx = None
        for i, row in enumerate(rows[:8]):
            folded = [_fold(x) for x in row]
            lv = next((j for j, x in enumerate(folded) if any(k in x for k in ("so du", "du no", "gia tri", "ty le"))), None)
            gr = next((j for j, x in enumerate(folded) if any(k in x for k in ("toc do tang", "tang (giam)", "tang truong", "so voi cuoi nam"))), None)
            if lv is not None or gr is not None:
                header_idx, level_idx, growth_idx = i, lv, gr
                break
        if header_idx is None:
            continue

        period = _reference_month(" ".join(" ".join(r) for r in rows[:4])) or page_period
        if period is None:
            continue

        header = rows[header_idx]
        for r in rows[header_idx + 1 :]:
            label = _first_non_numeric(r)
            if not label:
                continue
            folded_label = _fold(label)
            if folded_label in {"chi tieu", "stt", "tong"}:
                continue

            level = None
            growth = None
            if len(r) == len(header):
                if level_idx is not None and level_idx < len(r):
                    level = parse_percent(r[level_idx]) if page_id == "ldr" else parse_vn_number(r[level_idx])
                if growth_idx is not None and growth_idx < len(r):
                    growth = parse_percent(r[growth_idx])
            else:
                nums = _row_numbers(r, label)
                if page_id == "ldr":
                    level = nums[0] if nums else None
                    growth = nums[1] if len(nums) > 1 else None
                else:
                    big = [x for x in nums if abs(x) >= 1000]
                    small = [x for x in nums if abs(x) < 1000]
                    if len(big) == 1:
                        level = big[0]
                        growth = small[0] if small else None
                    else:
                        level = nums[0] if nums else None
                        growth = nums[1] if len(nums) > 1 else None

            if level is None and growth is None:
                continue
            key = (page_id, label, period, level, growth)
            if key in seen:
                continue
            seen.add(key)
            rows_out.append(MacroRow(page_id, label, period, level, growth))

    if not rows_out:
        raise SourceSchemaChanged(f"No SBV macro rows parsed for {page_id}")
    return rows_out


def fetch_page(page_id: str, *, timeout: int = 45) -> tuple[str, datetime, str]:
    slug = PAGES[page_id]
    url = BASE + slug
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    fetched_at = datetime.now(timezone.utc)
    if _looks_blocked(response.text):
        raise SourceBlocked(f"SBV WAF rejected {page_id}")
    return response.text, fetched_at, url


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
