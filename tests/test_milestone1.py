from pathlib import Path

from src.common.numbers import parse_percent, parse_vn_number
from src.ingestion.sbv_omo import looks_blocked, parse_omo_html
from src.jobs.sbv_omo_once import run


FIXTURE = Path(__file__).parent / "fixtures" / "sbv_omo_sample.html"
PREVIOUS = Path(__file__).parent / "fixtures" / "sbv_omo_previous.html"


def test_vietnamese_numbers():
    assert parse_vn_number("32.055,15") == 32055.15
    assert parse_vn_number("1.225.073") == 1225073.0


def test_percent_dot_and_comma_decimal():
    assert parse_percent("7,05") == 7.05
    assert parse_percent("7.05") == 7.05


def test_waf_detection():
    assert looks_blocked("The requested URL was rejected. Support ID: 123")
    assert not looks_blocked("<html>" + "x" * 6000 + "</html>")


def test_parse_omo_fixture():
    rows = parse_omo_html(FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert rows[0].session_date.isoformat() == "2026-09-28"
    assert rows[0].tenor_days == 7
    assert rows[0].volume_bn_vnd == 32055.15
    assert rows[1].rate_pct == 4.75


def test_vertical_slice_is_idempotent(tmp_path):
    db = tmp_path / "surveillance.db"
    raw = tmp_path / "raw"
    thresholds = Path(__file__).parents[1] / "config" / "thresholds.json"

    first = run(fixture=FIXTURE, db_path=db, raw_root=raw, thresholds_path=thresholds)
    second = run(fixture=FIXTURE, db_path=db, raw_root=raw, thresholds_path=thresholds)

    assert first["new_observations"] == 8
    assert second["new_observations"] == 0
    assert second["db_counts"]["market_observation"] == 8


def test_signal_generation_against_previous_session(tmp_path):
    db = tmp_path / "surveillance.db"
    raw = tmp_path / "raw"
    thresholds = Path(__file__).parents[1] / "config" / "thresholds.json"

    first = run(fixture=PREVIOUS, db_path=db, raw_root=raw, thresholds_path=thresholds)
    second = run(fixture=FIXTURE, db_path=db, raw_root=raw, thresholds_path=thresholds)

    assert first["new_signals"] == 0
    # 7D rate: +50bp; 7D volume: +167% => both HIGH under demo thresholds.
    assert second["new_signals"] >= 2
    assert second["db_counts"]["risk_signal"] >= 2
