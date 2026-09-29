from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path


def test_hnx_cbis_failures_are_degraded_not_global_failure(monkeypatch):
    import src.system.live_parser_smoke as m

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(m, "fetch_omo_html", lambda: ("omo", now))
    monkeypatch.setattr(m, "parse_omo_html", lambda html: [1])
    monkeypatch.setattr(m, "fetch_secondary_day", lambda d: (_ for _ in ()).throw(RuntimeError("TLS")))
    monkeypatch.setattr(m, "fetch_auctions", lambda a, b: (_ for _ in ()).throw(RuntimeError("TLS")))
    monkeypatch.setattr(m, "cbis_fetch_page", lambda url: (_ for _ in ()).throw(RuntimeError("TLS")))
    monkeypatch.setattr(m, "fetch_latest_articles", lambda: ([("u", "v", now)], now))
    monkeypatch.setattr(m, "parse_article_html", lambda html, url="", fetched_at=None: object())
    monkeypatch.setattr(m, "sbv_macro_fetch_page", lambda page_id: ("macro", now, "u"))
    monkeypatch.setattr(m, "parse_sbv_macro", lambda html, page_id="": [1])

    result = m.run_live_parser_smoke(hnx_date=date(2026, 9, 28))
    assert result["ok"] is True
    assert result["status"] == "DEGRADED"
    assert result["degraded_source_count"] == 7
    assert "HNX_GOV_SECONDARY" in result["degraded_sources"]
    assert "CBIS_DISCLOSURES" in result["degraded_sources"]


def test_core_source_failure_still_fails_smoke(monkeypatch):
    import src.system.live_parser_smoke as m

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(m, "fetch_omo_html", lambda: (_ for _ in ()).throw(RuntimeError("SBV down")))
    monkeypatch.setattr(m, "fetch_secondary_day", lambda d: ("sec", now))
    monkeypatch.setattr(m, "parse_secondary_html", lambda html, d: [])
    monkeypatch.setattr(m, "fetch_auctions", lambda a, b: ("auc", now))
    monkeypatch.setattr(m, "parse_auction_html", lambda html: [])
    monkeypatch.setattr(m, "cbis_fetch_page", lambda url: ("cbis", now))
    monkeypatch.setattr(m, "parse_issuer_list", lambda html: [1])
    monkeypatch.setattr(m, "parse_bond_list", lambda html: [1])
    monkeypatch.setattr(m, "parse_ratings", lambda html: [1])
    monkeypatch.setattr(m, "parse_disclosures", lambda html: [1])
    monkeypatch.setattr(m, "parse_trading_status", lambda html: [1])
    monkeypatch.setattr(m, "fetch_latest_articles", lambda: ([("u", "v", now)], now))
    monkeypatch.setattr(m, "parse_article_html", lambda html, url="", fetched_at=None: object())
    monkeypatch.setattr(m, "sbv_macro_fetch_page", lambda page_id: ("macro", now, "u"))
    monkeypatch.setattr(m, "parse_sbv_macro", lambda html, page_id="": [1])

    result = m.run_live_parser_smoke(hnx_date=date(2026, 9, 28))
    assert result["ok"] is False
    assert result["status"] == "FAILED"


def test_market_cycle_reports_degraded_when_some_sources_fail(monkeypatch, tmp_path):
    import src.jobs.market_cycle as m

    monkeypatch.setattr(m, "run_omo", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(m, "run_hnx_gov", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("TLS")))
    monkeypatch.setattr(m, "run_cbonds", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("TLS")))

    result = m.run_cycle(
        db_path=tmp_path / "x.db",
        raw_root=tmp_path / "raw",
        thresholds_path=Path("config/thresholds.json"),
    )
    assert result["status"] == "DEGRADED"
    assert result["success_count"] == 1
    assert result["failure_count"] == 2
    assert set(result["unavailable_sources"]) == {"hnx_gov", "hnx_cbonds"}
