from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.version import PROJECT_VERSION
from src.ingestion.sbv_omo import PARSER_VERSION, fetch_omo_html, parse_omo_html
from src.normalization.omo import to_market_observations
from src.signals.liquidity import build_omo_signals
from src.storage.factory import create_store
from src.storage.raw_archive import archive_html
from src.validation.observations import validate_batch

CODE_VERSION = PROJECT_VERSION


def load_thresholds(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(*, fixture: Path | None = None, db_path: Path, raw_root: Path, thresholds_path: Path) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)
    run_row = {
        "run_id": run_id,
        "source": "SBV",
        "worker": "sbv_omo_once",
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
        if fixture:
            html = fixture.read_text(encoding="utf-8")
            fetched_at = datetime.now(timezone.utc)
        else:
            html, fetched_at = fetch_omo_html()

        rows = parse_omo_html(html)
        raw_object_id, raw_hash = archive_html(
            html,
            source="sbv_omo",
            session_date=rows[0].session_date,
            local_root=raw_root,
        )
        observations = to_market_observations(
            rows,
            fetched_at=fetched_at,
            raw_path=raw_object_id,
            raw_hash=raw_hash,
        )
        valid, invalid = validate_batch(observations)

        thresholds = load_thresholds(thresholds_path)
        signals = build_omo_signals(valid, store, thresholds)
        new_count = store.insert_observations(valid)
        signal_count = store.insert_signals(signals)

        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "SUCCESS" if not invalid else "SUCCESS_WITH_INVALID",
            "records_downloaded": len(rows),
            "records_new": new_count,
            "records_invalid": len(invalid),
            "last_source_timestamp": rows[0].session_date.isoformat(),
        })
        store.insert_source_run(run_row)
        return {
            "run_id": run_id,
            "session_date": rows[0].session_date.isoformat(),
            "source_rows": len(rows),
            "valid_observations": len(valid),
            "invalid_observations": len(invalid),
            "new_observations": new_count,
            "new_signals": signal_count,
            "raw_object_id": raw_object_id,
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
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--thresholds", type=Path, default=Path("config/thresholds.json"))
    args = parser.parse_args()
    print(json.dumps(run(fixture=args.fixture, db_path=args.db, raw_root=args.raw_root, thresholds_path=args.thresholds), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
