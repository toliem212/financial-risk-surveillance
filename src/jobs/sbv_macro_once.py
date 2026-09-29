from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.version import PROJECT_VERSION
from src.ingestion.sbv_macro import PAGES, PARSER_VERSION, fetch_page, parse_page
from src.normalization.sbv_macro import to_market_observations
from src.storage.factory import create_store
from src.storage.raw_archive import archive_html
from src.validation.observations import validate_batch

CODE_VERSION = PROJECT_VERSION


def run(*, fixture_dir: Path | None, db_path: Path, raw_root: Path) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)
    run_row = {
        "run_id": run_id,
        "source": "SBV",
        "worker": "sbv_macro_once",
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
    total_rows = total_new = total_invalid = 0
    periods: list[str] = []
    pages_result: dict[str, dict] = {}
    try:
        source_errors = 0
        for page_id, slug in PAGES.items():
            try:
                if fixture_dir:
                    path = fixture_dir / f"{page_id}.html"
                    if not path.exists():
                        pages_result[page_id] = {"status": "SKIPPED", "reason": f"missing fixture {path.name}"}
                        continue
                    html = path.read_text(encoding="utf-8")
                    fetched_at = datetime.now(timezone.utc)
                    source_url = f"fixture://{path.name}"
                else:
                    html, fetched_at, source_url = fetch_page(page_id)

                rows = parse_page(html, page_id=page_id)
                period = rows[0].reference_month
                raw_id, raw_hash = archive_html(
                    html, source=f"sbv_macro_{page_id}", session_date=period, local_root=raw_root
                )
                observations = to_market_observations(
                    rows, fetched_at=fetched_at, raw_object_id=raw_id, raw_hash=raw_hash, source_url=source_url
                )
                valid, invalid = validate_batch(observations)
                added = store.insert_observations(valid)
                total_rows += len(rows)
                total_new += added
                total_invalid += len(invalid)
                periods.append(period.isoformat())
                pages_result[page_id] = {
                    "status": "SUCCESS" if not invalid else "SUCCESS_WITH_INVALID",
                    "rows": len(rows),
                    "observations": len(valid),
                    "new": added,
                    "invalid": len(invalid),
                    "period": period.isoformat(),
                    "raw_object_id": raw_id,
                }
            except Exception as page_exc:
                source_errors += 1
                pages_result[page_id] = {
                    "status": "FAILED",
                    "error_type": type(page_exc).__name__,
                    "error_message": str(page_exc)[:1000],
                }
                continue

        if source_errors == len(PAGES):
            raise RuntimeError("All SBV macro pages failed")


        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": ("PARTIAL_SUCCESS" if source_errors else ("SUCCESS" if total_invalid == 0 else "SUCCESS_WITH_INVALID")),
            "records_downloaded": total_rows,
            "records_new": total_new,
            "records_invalid": total_invalid,
            "last_source_timestamp": max(periods) if periods else None,
        })
        store.insert_source_run(run_row)
        return {
            "run_id": run_id,
            "pages": pages_result,
            "new_observations": total_new,
            "invalid_observations": total_invalid,
            "source_errors": source_errors,
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
    p = argparse.ArgumentParser()
    p.add_argument("--fixture-dir", type=Path)
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = p.parse_args()
    print(json.dumps(run(fixture_dir=args.fixture_dir, db_path=args.db, raw_root=args.raw_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
