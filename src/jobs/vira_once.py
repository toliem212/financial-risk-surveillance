from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.version import PROJECT_VERSION
from src.ingestion.vira import PARSER_VERSION, ViraArticle, fetch_latest_articles, parse_article_html
from src.normalization.vira import article_to_observations
from src.reconciliation.vira import ADDITIVE_WEEKLY_METRICS, derive_friday_residual, reconcile_with_primary
from src.storage.factory import create_store
from src.signals.fx import build_fx_signals
from src.storage.raw_archive import archive_html
from src.validation.observations import validate_batch

CODE_VERSION = PROJECT_VERSION


def _fixture_article(path: Path, url: str) -> tuple[ViraArticle, str, datetime]:
    html = path.read_text(encoding="utf-8")
    fetched = datetime.now(timezone.utc)
    return parse_article_html(html, url=url, fetched_at=fetched), html, fetched


def _live_articles() -> list[tuple[ViraArticle, str, datetime]]:
    items, _ = fetch_latest_articles()
    out = []
    for url, html, fetched_at in items:
        out.append((parse_article_html(html, url=url, fetched_at=fetched_at), html, fetched_at))
    return out


def run(*, daily_fixture: Path | None, weekly_fixture: Path | None, db_path: Path, raw_root: Path) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)
    run_row = {
        "run_id": run_id,
        "source": "VIRA",
        "worker": "vira_once",
        "started_at": started.isoformat(),
        "finished_at": None,
        "status": "RUNNING",
        "records_downloaded": 0,
        "records_new": 0,
        "records_changed": 0,
        "records_invalid": 0,
        "last_source_timestamp": None,
        "error_type": None,
        "error_message": None,
        "code_version": CODE_VERSION,
        "parser_version": PARSER_VERSION,
    }
    store.insert_source_run(run_row)

    try:
        if daily_fixture or weekly_fixture:
            articles: list[tuple[ViraArticle, str, datetime]] = []
            if daily_fixture:
                articles.append(_fixture_article(daily_fixture, "fixture://vira/daily"))
            if weekly_fixture:
                articles.append(_fixture_article(weekly_fixture, "fixture://vira/weekly"))
        else:
            articles = _live_articles()
        if not articles:
            raise RuntimeError("No VIRA daily/weekly articles discovered")

        all_valid: list[dict] = []
        all_invalid: list[dict] = []
        dq_signals: list[dict] = []
        weekly_flow_observations: list[dict] = []
        latest_source_ts: str | None = None

        # Normalize each article independently; this preserves article-level provenance.
        for article, html, fetched_at in articles:
            session_date = article.week_end or article.market_date or article.article_date.date()
            raw_object_id, raw_hash = archive_html(
                html,
                source=f"vira_{article.article_type.lower()}",
                session_date=session_date,
                local_root=raw_root,
            )
            observations = article_to_observations(
                article,
                fetched_at=fetched_at,
                raw_path=raw_object_id,
                raw_hash=raw_hash,
            )
            valid, invalid = validate_batch(observations)
            valid, rec_signals = reconcile_with_primary(valid, store)
            all_valid.extend(valid)
            all_invalid.extend(invalid)
            dq_signals.extend(rec_signals)
            weekly_flow_observations.extend([
                o for o in valid
                if o.get("observation_method") == "WEEKLY_AGGREGATE"
                and o.get("metric_id") in ADDITIVE_WEEKLY_METRICS
            ])
            latest_source_ts = max(latest_source_ts or "", article.article_date.isoformat())

        new_direct = store.insert_observations(all_valid)

        # Derive a Friday residual only when the weekly flow and all Mon-Thu direct
        # observations exist. If Friday is directly observed, no residual is created.
        derived: list[dict] = []
        for weekly in weekly_flow_observations:
            daily = store.observations_between(
                metric_id=weekly["metric_id"],
                entity_id=weekly["entity_id"],
                start_date=weekly["period_start"],
                end_date=weekly["period_end"],
                source="VIRA",
            )
            residual = derive_friday_residual(weekly, daily)
            if residual:
                valid_residual, invalid_residual = validate_batch([residual])
                derived.extend(valid_residual)
                all_invalid.extend(invalid_residual)

        new_derived = store.insert_observations(derived)
        thresholds = json.loads(Path("config/thresholds.json").read_text(encoding="utf-8"))
        fx_signals = build_fx_signals(all_valid + derived, store, thresholds)
        signal_count = store.insert_signals(dq_signals + fx_signals)

        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "SUCCESS" if not all_invalid else "SUCCESS_WITH_INVALID",
            "records_downloaded": len(articles),
            "records_new": new_direct + new_derived,
            "records_changed": len(derived),
            "records_invalid": len(all_invalid),
            "last_source_timestamp": latest_source_ts,
        })
        store.insert_source_run(run_row)
        return {
            "run_id": run_id,
            "articles": len(articles),
            "valid_observations": len(all_valid),
            "derived_residuals": len(derived),
            "invalid_observations": len(all_invalid),
            "new_observations": new_direct + new_derived,
            "new_signals": signal_count,
            "fx_signals_generated": len(fx_signals),
            "data_quality_signals_generated": len(dq_signals),
            "storage_backend": "postgres" if os.getenv("DATABASE_URL", "").strip() else "sqlite",
            "db_counts": store.counts(),
        }
    except Exception as exc:
        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
        })
        store.insert_source_run(run_row)
        raise
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-fixture", type=Path)
    parser.add_argument("--weekly-fixture", type=Path)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    result = run(
        daily_fixture=args.daily_fixture,
        weekly_fixture=args.weekly_fixture,
        db_path=args.db,
        raw_root=args.raw_root,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
