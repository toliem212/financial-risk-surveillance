from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from src.ingestion.hnx_gov import (
    canonical_tenor,
    parse_auction_html,
    parse_hnx_number,
    parse_secondary_html,
)
from src.jobs.hnx_gov_once import run
from src.normalization.hnx_gov import secondary_to_observations

FIX = Path(__file__).parent / "fixtures"


def test_hnx_number_formats():
    assert parse_hnx_number("1.234.567") == 1234567.0
    assert parse_hnx_number("4,0003") == 4.0003
    assert parse_hnx_number("2.35") == 2.35
    assert parse_hnx_number("20.619.000.000.000") == 20619000000000.0


def test_tenor_normalization():
    assert canonical_tenor("5 Năm") == "5Y"
    assert canonical_tenor("10 năm") == "10Y"
    assert canonical_tenor("1800 ngày") == "5Y"


def test_parse_secondary_and_derived_curve(tmp_path):
    html = (FIX / "hnx_secondary_current.html").read_text(encoding="utf-8")
    rows = parse_secondary_html(html, date(2026, 9, 25))
    assert len(rows) == 4
    assert rows[1].bond_code == "TD2636024"
    assert rows[1].ytm_pct == 4.46
    obs = secondary_to_observations(
        rows,
        fetched_at=datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc),
        raw_path="fixture.html",
        raw_hash="abc",
    )
    curve = [o for o in obs if o["metric_id"] == "HNX.GOV.TENOR_YIELD"]
    assert {o["entity_id"] for o in curve} == {"GOV_TENOR:5Y", "GOV_TENOR:10Y", "GOV_TENOR:15Y"}
    y10 = next(o for o in curve if o["entity_id"] == "GOV_TENOR:10Y")
    assert round(y10["value"], 4) == round((4.46 * 20 + 4.48 * 10) / 30, 4)
    assert y10["quality_flag"] == "B"


def test_parse_auction():
    html = (FIX / "hnx_auction_sample.html").read_text(encoding="utf-8")
    rows = parse_auction_html(html)
    assert len(rows) == 4
    assert rows[0].auction_date == date(2026, 9, 23)
    assert rows[2].awarded_value_vnd == 20619000000000.0
    assert rows[2].auction_yield_pct == 4.43


def test_parse_current_hnx_auction_schema():
    html = (FIX / "hnx_auction_current_schema.html").read_text(encoding="utf-8")
    rows = parse_auction_html(html)
    assert len(rows) == 2
    first = rows[0]
    # Current HNX calls this field "Ngày TCPH"; do not substitute "Ngày phát hành".
    assert first.auction_date == date(2026, 9, 23)
    assert first.auction_round == "PH.168.2026"
    assert first.issue_type == "Đơn giá"
    assert first.offered_value_vnd == 500000000000.0
    assert first.awarded_value_vnd == 50000000000.0
    assert first.additional_awarded_value_vnd == 0.0
    assert first.nominal_coupon_pct == 4.4
    assert first.auction_yield_pct == 4.62
    assert first.registered_yield_low_pct == 4.62
    assert first.registered_yield_high_pct == 4.62


def test_end_to_end_rates_signals_and_idempotency(tmp_path, monkeypatch):
    db = tmp_path / "m3.db"
    raw = tmp_path / "raw"
    thresholds = Path(__file__).parents[1] / "config" / "thresholds.json"
    monkeypatch.delenv("DATABASE_URL", raising=False)

    first = run(
        target_date=date(2026, 9, 24), db_path=db, raw_root=raw, thresholds_path=thresholds,
        secondary_fixture=FIX / "hnx_secondary_previous.html",
        auction_fixture=FIX / "hnx_auction_sample.html",
    )
    assert first["new_observations"] > 0
    assert first["new_signals"] == 0

    second = run(
        target_date=date(2026, 9, 25), db_path=db, raw_root=raw, thresholds_path=thresholds,
        secondary_fixture=FIX / "hnx_secondary_current.html",
        auction_fixture=FIX / "hnx_auction_sample.html",
    )
    assert second["new_observations"] > 0
    assert second["new_signals"] >= 2

    repeat = run(
        target_date=date(2026, 9, 25), db_path=db, raw_root=raw, thresholds_path=thresholds,
        secondary_fixture=FIX / "hnx_secondary_current.html",
        auction_fixture=FIX / "hnx_auction_sample.html",
    )
    assert repeat["new_observations"] == 0
    assert repeat["new_signals"] == 0
