from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests

from src.common.http import resilient_session
from bs4 import BeautifulSoup

BASE_DOMAIN = "https://vira.org.vn"
BULLETIN_LIST_URL = "https://vira.org.vn/tin/Ban-tin.html"
DAILY_LIST_URL = "https://vira.org.vn/tin/Ban-tin-Kinh-te-Tai-chinh-ngay.html"
WEEKLY_LIST_URL = "https://vira.org.vn/tin/Tong-hop-tin-kinh-te-tai-chinh-tuan.html"
PARSER_VERSION = "vira-semantic-v1.1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
LOCAL_TZ = ZoneInfo("Asia/Bangkok")


@dataclass(frozen=True)
class ViraArticle:
    article_type: str  # DAILY / WEEKLY
    title: str
    article_date: datetime
    market_date: date | None
    market_date_inferred: bool
    week_start: date | None
    week_end: date | None
    url: str
    text: str
    publication_time_inferred: bool = False


def fetch_html(url: str, timeout: int = 25) -> tuple[str, datetime]:
    session = resilient_session(user_agent=HEADERS["User-Agent"], retries=2)
    response = session.get(url, timeout=(10, timeout), allow_redirects=True)
    response.raise_for_status()
    return response.text, datetime.now(ZoneInfo("UTC"))


def _main_text(soup: BeautifulSoup) -> str:
    main = soup.find("div", class_="detail-news-content")
    if main is None:
        main = soup.body or soup
    return " ".join(main.stripped_strings)


def _parse_source_timestamp(text: str) -> datetime | None:
    patterns = [
        # Article pages commonly show: 07:59 25/09/2026
        r"\b(\d{1,2}):(\d{2})\s+(\d{1,2})/(\d{1,2})/(\d{4})\b",
        # Listing/cards may expose: 25/09/2026 07:59
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b",
    ]
    for idx, pattern in enumerate(patterns):
        m = re.search(pattern, text)
        if not m:
            continue
        if idx == 0:
            hh, mm, dd, mon, yy = map(int, m.groups())
        else:
            dd, mon, yy, hh, mm = map(int, m.groups())
        return datetime(yy, mon, dd, hh, mm, tzinfo=LOCAL_TZ)
    return None


def _published_at(soup: BeautifulSoup, text: str, fallback: datetime | None = None) -> tuple[datetime, bool]:
    parsed = _parse_source_timestamp(text)
    if parsed is not None:
        return parsed, False

    # Prefer explicit machine-readable publication metadata when visible text changed.
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"itemprop": "datePublished"},
    ):
        node = soup.find("meta", attrs=attrs)
        raw = str(node.get("content", "")).strip() if node else ""
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LOCAL_TZ)
            return dt.astimezone(LOCAL_TZ), False
        except ValueError:
            parsed = _parse_source_timestamp(raw)
            if parsed is not None:
                return parsed, False

    # Conservative fallback for live collection: first-observed time. This never
    # makes an article appear available earlier than the crawler actually saw it.
    if fallback is not None:
        return fallback.astimezone(LOCAL_TZ), True
    raise ValueError("VIRA publication timestamp not found")


def _date_with_article_year(day: int, month: int, article_date: datetime) -> date:
    year = article_date.year
    if article_date.month == 1 and month == 12:
        year -= 1
    return date(year, month, day)


def _daily_market_date(text: str, article_date: datetime) -> date | None:
    # Prefer explicit market-session wording; do not infer from publication date unless needed.
    patterns = [
        r"Thị trường ngoại tệ:\s*Phiên\s+(\d{1,2})/(\d{1,2})",
        r"Thị trường tiền tệ LNH:\s*Ngày\s+(\d{1,2})/(\d{1,2})",
        r"\bPhiên\s+(\d{1,2})/(\d{1,2})\b",
        r"\bNgày\s+(\d{1,2})/(\d{1,2})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE)
        if m:
            return _date_with_article_year(int(m.group(1)), int(m.group(2)), article_date)
    return None


def _week_range(title: str) -> tuple[date | None, date | None]:
    m = re.search(
        r"tuần\s+(\d{1,2})/(\d{1,2})\s*[-–]\s*(\d{1,2})/(\d{1,2})/(\d{4})",
        title,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if not m:
        return None, None
    d1, m1, d2, m2, yy = map(int, m.groups())
    return date(yy, m1, d1), date(yy, m2, d2)


def parse_article_html(html: str, *, url: str = "fixture://vira", fetched_at: datetime | None = None) -> ViraArticle:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = " ".join(h1.stripped_strings) if h1 else ""
    full_text = " ".join(soup.stripped_strings)
    text = _main_text(soup)
    published, publication_time_inferred = _published_at(soup, full_text, fallback=fetched_at)

    if re.search(r"Tổng hợp\s+Kinh tế\s*-\s*Tài chính\s+tuần", title, flags=re.IGNORECASE):
        week_start, week_end = _week_range(title)
        if week_start is None or week_end is None:
            raise ValueError(f"VIRA weekly range not found in title: {title}")
        return ViraArticle(
            article_type="WEEKLY",
            title=title,
            article_date=published,
            market_date=None,
            market_date_inferred=False,
            week_start=week_start,
            week_end=week_end,
            url=url,
            text=text,
            publication_time_inferred=publication_time_inferred,
        )

    if "Bản tin Kinh tế - Tài chính ngày" in title:
        market_date = _daily_market_date(text, published)
        inferred = market_date is None
        if inferred:
            # Fallback is explicit and will be downgraded by normalization.
            market_date = published.date()
        return ViraArticle(
            article_type="DAILY",
            title=title,
            article_date=published,
            market_date=market_date,
            market_date_inferred=inferred,
            week_start=None,
            week_end=None,
            url=url,
            text=text,
            publication_time_inferred=publication_time_inferred,
        )

    raise ValueError(f"Unsupported VIRA article title: {title}")


def discover_latest_article_urls(listing_html: str) -> dict[str, str]:
    """Discover article-detail URLs, never category/listing URLs.

    VIRA navigation links use names that are substrings of the article URLs.
    Matching only on "Ban-tin-Kinh-te-Tai-chinh-ngay" therefore mistakenly
    selected the category page. Require the extra path segment that identifies
    an article detail page.
    """
    soup = BeautifulSoup(listing_html, "html.parser")
    daily: list[str] = []
    weekly: list[str] = []
    for a in soup.find_all("a", href=True):
        href = unescape(str(a.get("href", ""))).strip()
        absolute = urljoin(BASE_DOMAIN, href)
        path = absolute.split("?", 1)[0]
        if re.search(r"/tin/Ban-tin-Kinh-te-Tai-chinh-ngay/[^/]+\.html$", path, flags=re.IGNORECASE):
            if absolute not in daily:
                daily.append(absolute)
        if re.search(r"/tin/Tong-hop-tin-kinh-te-tai-chinh-tuan/[^/]+\.html$", path, flags=re.IGNORECASE):
            if absolute not in weekly:
                weekly.append(absolute)
    out: dict[str, str] = {}
    if daily:
        out["DAILY"] = daily[0]
    if weekly:
        out["WEEKLY"] = weekly[0]
    return out


def _merge_discovered(target: dict[str, str], listing_html: str) -> None:
    for key, value in discover_latest_article_urls(listing_html).items():
        target.setdefault(key, value)


def fetch_latest_articles() -> tuple[list[tuple[str, str, datetime]], datetime]:
    # Start from the combined bulletin page. If one family is not visible among
    # the newest cards, fall back to its dedicated category page.
    listing, listing_fetched = fetch_html(BULLETIN_LIST_URL)
    urls: dict[str, str] = {}
    _merge_discovered(urls, listing)

    if "DAILY" not in urls:
        daily_listing, _ = fetch_html(DAILY_LIST_URL)
        _merge_discovered(urls, daily_listing)
    if "WEEKLY" not in urls:
        weekly_listing, _ = fetch_html(WEEKLY_LIST_URL)
        _merge_discovered(urls, weekly_listing)

    out: list[tuple[str, str, datetime]] = []
    for article_type in ("DAILY", "WEEKLY"):
        url = urls.get(article_type)
        if not url:
            continue
        html, fetched_at = fetch_html(url)
        out.append((url, html, fetched_at))
    return out, listing_fetched

