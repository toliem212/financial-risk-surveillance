from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.hnx_cbonds import (
    parse_bond_list, parse_disclosures, parse_issuer_list, parse_number, parse_ratings, parse_trading_status,
)
from src.jobs.hnx_cbonds_once import run
from src.normalization.hnx_cbonds import disclosures_to_events, trading_status_to_events
from src.signals.corporate_bond import event_signals
from src.storage.sqlite_store import SQLiteStore

FIX = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_cbonds_number_parser():
    assert parse_number("1,000,000,000") == 1_000_000_000
    assert parse_number("67,988") == 67_988
    assert parse_number("4,05") == 4.05


def test_cbonds_master_parsers():
    issuers = parse_issuer_list(_read("cbis_issuers_sample.html"))
    bonds = parse_bond_list(_read("cbis_bonds_sample.html"))
    assert issuers[0].issuer_code == "ABB"
    assert issuers[0].sector == "Tổ chức tín dụng"
    assert bonds[0].trading_code == "AAS12201"
    assert bonds[1].face_value_vnd == 1_000_000_000


def test_cbonds_rating_parser_keeps_agency_scale():
    rows = parse_ratings(_read("cbis_ratings_sample.html"))
    assert rows[0].rating == "A+"
    assert rows[0].agency == "VIS Ratings"
    assert rows[1].rating == "B2"
    assert rows[1].agency == "Moody's Ratings"


def test_disclosure_taxonomy():
    rows = parse_disclosures(_read("cbis_disclosures_sample.html"))
    events = disclosures_to_events(rows, datetime(2026, 9, 29, tzinfo=timezone.utc))
    types = {e["event_type"] for e in events}
    assert "TERM_CHANGE" in types
    assert "PAYMENT_DELAY" in types
    assert "MATURITY_EXTENSION" in types
    assert "COLLATERAL_CHANGE" in types
    assert all("Báo cáo tài chính" not in e["event_payload"]["title"] for e in events)


def test_trading_status_taxonomy():
    rows = parse_trading_status(_read("cbis_status_sample.html"))
    events = trading_status_to_events(rows, datetime(2026, 9, 29, tzinfo=timezone.utc))
    types = {e["event_type"] for e in events}
    assert {"REGISTRATION", "TRADING_SUSPENSION", "DELISTING"}.issubset(types)
    suspension = [e for e in events if e["event_type"] == "TRADING_SUSPENSION"][0]
    assert suspension["event_payload"]["reason"] == "Mua lại"


def test_event_signals_are_deterministic_and_not_all_events_alert():
    rows = parse_trading_status(_read("cbis_status_sample.html"))
    events = trading_status_to_events(rows, datetime(2026, 9, 29, tzinfo=timezone.utc))
    signals = event_signals(events)
    assert not any(s["signal_type"] == "CB_REGISTRATION" for s in signals)
    assert not any(s["signal_type"] == "CB_TRADING_SUSPENSION" for s in signals)  # buyback-driven suspension is informational


def test_milestone4_job_is_idempotent(tmp_path):
    kwargs = dict(
        db_path=tmp_path / "surveillance.db", raw_root=tmp_path / "raw",
        issuer_fixture=FIX / "cbis_issuers_sample.html", bond_fixture=FIX / "cbis_bonds_sample.html",
        rating_fixture=FIX / "cbis_ratings_sample.html", disclosure_fixture=FIX / "cbis_disclosures_sample.html",
        status_fixture=FIX / "cbis_status_sample.html",
    )
    first = run(**kwargs)
    second = run(**kwargs)
    assert first["inserted"]["events"] > 0
    assert second["inserted"]["events"] == 0
    store = SQLiteStore(tmp_path / "surveillance.db")
    try:
        counts = store.counts()
        assert counts["issuer_master"] >= 2
        assert counts["bond_master"] == 2
        assert counts["bond_event"] > 0
    finally:
        store.close()
