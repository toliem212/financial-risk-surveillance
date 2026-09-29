from datetime import date, datetime, timezone
from pathlib import Path

from src.ingestion.hnx_gov import parse_auction_html, parse_secondary_html
from src.ingestion.sbv_macro import parse_page as parse_macro_page
from src.ingestion.sbv_omo import parse_omo_html
from src.ingestion.vira import parse_article_html
from src.normalization.hnx_gov import auctions_to_observations, secondary_to_observations
from src.normalization.omo import to_market_observations as omo_to_observations
from src.normalization.sbv_macro import to_market_observations as macro_to_observations
from src.normalization.vira import article_to_observations
from src.signals.corporate_bond import event_signals

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)


def _identity(rows):
    return [(x["observation_id"], x["record_hash"]) for x in rows]


def test_sbv_omo_identity_does_not_depend_on_raw_html_hash():
    rows = parse_omo_html((FIX / "sbv_omo_sample.html").read_text(encoding="utf-8"))
    a = omo_to_observations(rows, fetched_at=NOW, raw_path="raw/a.html", raw_hash="raw-hash-a")
    b = omo_to_observations(rows, fetched_at=NOW, raw_path="raw/b.html", raw_hash="raw-hash-b")
    assert _identity(a) == _identity(b)


def test_vira_identity_does_not_depend_on_raw_html_hash():
    html = (FIX / "vira_daily_sample.html").read_text(encoding="utf-8")
    article = parse_article_html(html, url="fixture://vira/daily", fetched_at=NOW)
    a = article_to_observations(article, fetched_at=NOW, raw_path="raw/a.html", raw_hash="raw-hash-a")
    b = article_to_observations(article, fetched_at=NOW, raw_path="raw/b.html", raw_hash="raw-hash-b")
    assert _identity(a) == _identity(b)


def test_sbv_macro_identity_does_not_depend_on_raw_html_hash():
    html = (FIX / "sbv_macro" / "m2.html").read_text(encoding="utf-8")
    rows = parse_macro_page(html, page_id="m2")
    a = macro_to_observations(rows, fetched_at=NOW, raw_object_id="raw/a.html", raw_hash="raw-hash-a", source_url="fixture://m2")
    b = macro_to_observations(rows, fetched_at=NOW, raw_object_id="raw/b.html", raw_hash="raw-hash-b", source_url="fixture://m2")
    assert _identity(a) == _identity(b)


def test_hnx_aggregate_and_auction_identity_do_not_depend_on_raw_html_hash():
    secondary = parse_secondary_html(
        (FIX / "hnx_secondary_current.html").read_text(encoding="utf-8"),
        date(2026, 9, 25),
    )
    a = secondary_to_observations(secondary, fetched_at=NOW, raw_path="raw/a.html", raw_hash="raw-hash-a")
    b = secondary_to_observations(secondary, fetched_at=NOW, raw_path="raw/b.html", raw_hash="raw-hash-b")
    assert _identity(a) == _identity(b)

    auctions = parse_auction_html((FIX / "hnx_auction_current_schema.html").read_text(encoding="utf-8"))
    c = auctions_to_observations(auctions, fetched_at=NOW, raw_path="raw/c.html", raw_hash="raw-hash-c")
    d = auctions_to_observations(auctions, fetched_at=NOW, raw_path="raw/d.html", raw_hash="raw-hash-d")
    assert _identity(c) == _identity(d)


def test_unclassified_cb_disclosure_is_timeline_only_not_alert():
    event = {
        "event_hash": "event-hash-1",
        "event_type": "OTHER_MATERIAL_DISCLOSURE",
        "issuer_id": "issuer-1",
        "bond_id": None,
        "event_date": "2026-09-28",
        "source": "HNX_CBIS",
        "source_url": "https://cbonds.hnx.vn/",
        "event_payload": {"title": "Thông tin công bố khác"},
        "quality_flag": "A",
    }
    assert event_signals([event]) == []
