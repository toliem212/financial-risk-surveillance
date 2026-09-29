from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.version import PROJECT_VERSION
from src.ingestion.hnx_gov import (
    PARSER_VERSION,
    fetch_auctions,
    fetch_secondary_day,
    parse_auction_html,
    parse_secondary_html,
)
from src.normalization.hnx_gov import auctions_to_observations, secondary_to_observations
from src.signals.rates import build_gov_yield_signals
from src.storage.factory import create_store
from src.storage.raw_archive import archive_html
from src.validation.observations import validate_batch

CODE_VERSION = PROJECT_VERSION


def _thresholds(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    *, target_date: date, db_path: Path, raw_root: Path, thresholds_path: Path,
    secondary_fixture: Path | None = None, auction_fixture: Path | None = None,
) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)
    run_row = {
        "run_id": run_id, "source": "HNX_GOV", "worker": "hnx_gov_once",
        "started_at": started.isoformat(), "finished_at": None, "status": "RUNNING",
        "records_downloaded": 0, "records_new": 0, "records_changed": 0,
        "records_invalid": 0, "last_source_timestamp": None, "error_type": None,
        "error_message": None, "code_version": CODE_VERSION, "parser_version": PARSER_VERSION,
    }
    store.insert_source_run(run_row)
    try:
        if secondary_fixture:
            sec_html = secondary_fixture.read_text(encoding="utf-8")
            sec_fetched = datetime.now(timezone.utc)
        else:
            sec_html, sec_fetched = fetch_secondary_day(target_date)
        sec_rows = parse_secondary_html(sec_html, target_date)
        sec_raw, sec_hash = archive_html(sec_html, source="hnx_gov_secondary", session_date=target_date, local_root=raw_root)
        sec_obs = secondary_to_observations(sec_rows, fetched_at=sec_fetched, raw_path=sec_raw, raw_hash=sec_hash)

        auction_start = target_date - timedelta(days=14)
        if auction_fixture:
            auc_html = auction_fixture.read_text(encoding="utf-8")
            auc_fetched = datetime.now(timezone.utc)
        else:
            auc_html, auc_fetched = fetch_auctions(auction_start, target_date)
        auc_rows = parse_auction_html(auc_html)
        auc_raw, auc_hash = archive_html(auc_html, source="hnx_gov_auctions", session_date=target_date, local_root=raw_root)
        auc_obs = auctions_to_observations(auc_rows, fetched_at=auc_fetched, raw_path=auc_raw, raw_hash=auc_hash)

        valid, invalid = validate_batch(sec_obs + auc_obs)
        signals = build_gov_yield_signals(valid, store, _thresholds(thresholds_path))
        new_count = store.insert_observations(valid)
        signal_count = store.insert_signals(signals)
        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "SUCCESS" if not invalid else "SUCCESS_WITH_INVALID",
            "records_downloaded": len(sec_rows) + len(auc_rows),
            "records_new": new_count,
            "records_invalid": len(invalid),
            "last_source_timestamp": target_date.isoformat(),
        })
        store.insert_source_run(run_row)
        return {
            "run_id": run_id,
            "target_date": target_date.isoformat(),
            "secondary_rows": len(sec_rows), "auction_rows": len(auc_rows),
            "valid_observations": len(valid), "invalid_observations": len(invalid),
            "new_observations": new_count, "new_signals": signal_count,
            "storage_backend": "postgres" if os.getenv("DATABASE_URL", "").strip() else "sqlite",
            "db_counts": store.counts(),
        }
    except Exception as exc:
        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(), "status": "FAILED",
            "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
        })
        store.insert_source_run(run_row)
        raise
    finally:
        store.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=date.fromisoformat, default=date.today())
    p.add_argument("--secondary-fixture", type=Path)
    p.add_argument("--auction-fixture", type=Path)
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--thresholds", type=Path, default=Path("config/thresholds.json"))
    args = p.parse_args()
    print(json.dumps(run(
        target_date=args.date, db_path=args.db, raw_root=args.raw_root,
        thresholds_path=args.thresholds, secondary_fixture=args.secondary_fixture,
        auction_fixture=args.auction_fixture,
    ), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
