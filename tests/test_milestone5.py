from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.vira import discover_latest_article_urls, parse_article_html
from src.jobs.vira_once import run
from src.normalization.vira import article_to_observations
from src.reconciliation.vira import derive_friday_residual, reconcile_with_primary
from src.storage.sqlite_store import SQLiteStore

FIX = Path(__file__).parent / "fixtures"


def _normalize(name: str):
    html = (FIX / name).read_text(encoding="utf-8")
    article = parse_article_html(html, url=f"fixture://{name}")
    return article, article_to_observations(
        article,
        fetched_at=datetime(2026, 9, 29, tzinfo=timezone.utc),
        raw_path=f"raw/{name}",
        raw_hash="abc123",
    )


def _find(rows, metric_id, entity_id=None):
    matches = [r for r in rows if r["metric_id"] == metric_id and (entity_id is None or r["entity_id"] == entity_id)]
    assert matches, (metric_id, entity_id)
    return matches[0]


def test_vira_listing_discovery():
    html = (FIX / "vira_listing_sample.html").read_text(encoding="utf-8")
    urls = discover_latest_article_urls(html)
    assert "25-09-2026" in urls["DAILY"]
    assert "21-09-25-09-2026" in urls["WEEKLY"]
    assert not urls["DAILY"].endswith("Ban-tin-Kinh-te-Tai-chinh-ngay.html")
    assert not urls["WEEKLY"].endswith("Tong-hop-tin-kinh-te-tai-chinh-tuan.html")


def test_daily_semantics_and_numeric_parsing():
    article, rows = _normalize("vira_daily_sample.html")
    assert article.market_date.isoformat() == "2026-07-14"
    assert article.market_date_inferred is False
    assert _find(rows, "VIRA.FX.CENTRAL")["value"] == 25225.0
    assert _find(rows, "VIRA.IBOR.RATE", "IBOR:USD:1W")["value"] == 3.71
    assert _find(rows, "VIRA.GOV.YIELD", "GOV_TENOR:10Y")["value"] == 4.40

    tender = _find(rows, "VIRA.OMO.REPO.TENDER")
    win = _find(rows, "VIRA.OMO.REPO.WIN")
    outstanding = _find(rows, "VIRA.OMO.REPO.OUTSTANDING")
    assert tender["value"] == 3000.0  # 1,000 at each of 3 explicit tenors
    assert win["value"] == 1339.77
    assert tender["measure_type"] == "FLOW"
    assert tender["observation_method"] == "DIRECT_DAILY"
    assert outstanding["measure_type"] == "STOCK"
    assert outstanding["period_start"] == outstanding["period_end"] == "2026-07-14"


def test_weekly_snapshot_flow_stock_are_not_merged():
    article, rows = _normalize("vira_weekly_sample.html")
    assert article.week_start.isoformat() == "2026-09-07"
    assert article.week_end.isoformat() == "2026-09-11"

    fx = _find(rows, "VIRA.FX.INTERBANK")
    ibor = _find(rows, "VIRA.IBOR.RATE", "IBOR:VND:ON")
    gov = _find(rows, "VIRA.GOV.YIELD", "GOV_TENOR:10Y")
    win = _find(rows, "VIRA.OMO.REPO.WIN")
    outstanding = _find(rows, "VIRA.OMO.REPO.OUTSTANDING")

    for snapshot in (fx, ibor, gov, outstanding):
        assert snapshot["period_start"] == snapshot["period_end"] == "2026-09-11"
        assert snapshot["observation_method"] == "DIRECT_WEEKLY_EOP"
    assert win["period_start"] == "2026-09-07"
    assert win["period_end"] == "2026-09-11"
    assert win["observation_method"] == "WEEKLY_AGGREGATE"
    assert win["value"] == 47259.02


def _daily_flow(day: str, value: float, idx: int):
    return {
        "observation_id": f"d{idx}", "metric_id": "VIRA.OMO.REPO.WIN", "entity_type": "OMO_REPO",
        "entity_id": "VIRA_OMO:REPO", "value": value, "unit": "VND_bn",
        "period_start": day, "period_end": day, "measure_type": "FLOW", "frequency": "DAILY",
        "source": "VIRA", "observation_method": "DIRECT_DAILY", "record_hash": f"h{idx}",
    }


def test_friday_residual_is_derived_only_for_additive_flow():
    weekly = {
        "observation_id": "w1", "metric_id": "VIRA.OMO.REPO.WIN", "entity_type": "OMO_REPO",
        "entity_id": "VIRA_OMO:REPO", "value": 100.0, "unit": "VND_bn",
        "period_start": "2026-09-07", "period_end": "2026-09-11", "measure_type": "FLOW",
        "frequency": "WEEKLY", "source": "VIRA", "source_url": "fixture://weekly",
        "source_published_at": "2026-09-14T08:00:00+07:00", "first_observed_at": "2026-09-14T01:00:00+00:00",
        "fetched_at": "2026-09-14T01:00:00+00:00", "raw_object_id": "raw", "parser_version": "v",
        "observation_method": "WEEKLY_AGGREGATE", "quality_flag": "C", "record_hash": "wh", "dims_json": "{}",
    }
    daily = [
        _daily_flow("2026-09-07", 10, 1), _daily_flow("2026-09-08", 20, 2),
        _daily_flow("2026-09-09", 30, 3), _daily_flow("2026-09-10", 15, 4),
    ]
    friday = derive_friday_residual(weekly, daily)
    assert friday is not None
    assert friday["value"] == 25.0
    assert friday["period_end"] == "2026-09-11"
    assert friday["observation_method"] == "DERIVED_RESIDUAL"
    assert friday["quality_flag"] == "B"

    stock = dict(weekly, metric_id="VIRA.OMO.REPO.OUTSTANDING", measure_type="STOCK")
    assert derive_friday_residual(stock, daily) is None


def test_gov_reconciliation_upgrades_match_and_flags_mismatch(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite")
    base = {
        "observation_id": "p1", "metric_id": "HNX.GOV.TENOR_YIELD", "entity_type": "GOV_TENOR",
        "entity_id": "GOV_TENOR:10Y", "value": 4.46, "unit": "pct",
        "period_start": "2026-09-11", "period_end": "2026-09-11", "as_of_time": None,
        "measure_type": "SNAPSHOT", "frequency": "DAILY", "source": "HNX", "source_url": "x",
        "source_published_at": None, "first_observed_at": "2026-09-11T09:00:00+00:00",
        "fetched_at": "2026-09-11T09:00:00+00:00", "processed_at": "2026-09-11T09:00:00+00:00",
        "observation_method": "DERIVED_CALCULATION", "quality_flag": "B", "raw_object_id": "x",
        "parser_version": "x", "record_hash": "p1", "dims_json": "{}",
    }
    store.insert_observations([base])
    _, rows = _normalize("vira_weekly_sample.html")
    gov = _find(rows, "VIRA.GOV.YIELD", "GOV_TENOR:10Y")
    enriched, signals = reconcile_with_primary([gov], store)
    assert enriched[0]["quality_flag"] == "B"
    assert json.loads(enriched[0]["dims_json"])["reconciliation"]["status"] == "MATCH"
    assert signals == []

    bad = dict(gov, value=4.80, observation_id="bad", record_hash="bad")
    enriched, signals = reconcile_with_primary([bad], store)
    assert enriched[0]["quality_flag"] == "D"
    assert signals and signals[0]["signal_type"] == "SOURCE_MISMATCH"
    store.close()


def test_vira_job_is_idempotent(tmp_path):
    kwargs = dict(
        daily_fixture=FIX / "vira_daily_sample.html",
        weekly_fixture=FIX / "vira_weekly_sample.html",
        db_path=tmp_path / "surveillance.db",
        raw_root=tmp_path / "raw",
    )
    first = run(**kwargs)
    second = run(**kwargs)
    assert first["new_observations"] > 0
    assert second["new_observations"] == 0
