from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.ingestion.hnx_gov import (
    PARSER_VERSION,
    fetch_secondary_day,
    parse_secondary_html,
)
from src.normalization.hnx_gov import secondary_to_observations
from src.storage.factory import create_store
from src.storage.raw_archive import archive_html
from src.validation.observations import validate_batch
from src.version import PROJECT_VERSION

CODE_VERSION = PROJECT_VERSION


def _business_days(start_date: date, end_date: date):
    d = start_date
    while d <= end_date:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def run(
    *,
    start_date: date,
    end_date: date,
    db_path: Path,
    raw_root: Path,
    sleep_ms: int = 200,
) -> dict:
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    days = list(_business_days(start_date, end_date))
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)

    run_row = {
        "run_id": run_id,
        "source": "HNX_GOV_BACKFILL",
        "worker": "hnx_gov_secondary_backfill",
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

    results: list[dict] = []
    total_rows = 0
    total_new = 0
    total_invalid = 0
    successful_days = 0
    failed_days = 0
    no_data_days = 0
    last_success_date: str | None = None

    try:
        total = len(days)

        for i, target_date in enumerate(days, start=1):
            t0 = time.perf_counter()

            try:
                html, fetched_at = fetch_secondary_day(target_date)
                rows = parse_secondary_html(html, target_date)

                raw_path, raw_hash = archive_html(
                    html,
                    source="hnx_gov_secondary",
                    session_date=target_date,
                    local_root=raw_root,
                )

                observations = secondary_to_observations(
                    rows,
                    fetched_at=fetched_at,
                    raw_path=raw_path,
                    raw_hash=raw_hash,
                )
                valid, invalid = validate_batch(observations)
                new_count = store.insert_observations(valid)

                total_rows += len(rows)
                total_new += new_count
                total_invalid += len(invalid)
                successful_days += 1
                last_success_date = target_date.isoformat()

                if len(rows) == 0:
                    no_data_days += 1
                    day_status = "NO_DATA"
                else:
                    day_status = "OK"

                elapsed = time.perf_counter() - t0
                print(
                    f"[{i:>3}/{total}] {target_date.isoformat()} "
                    f"{day_status:<7} rows={len(rows):>3} "
                    f"new={new_count:>3} invalid={len(invalid):>2} "
                    f"{elapsed:>5.1f}s",
                    flush=True,
                )

                results.append(
                    {
                        "date": target_date.isoformat(),
                        "status": day_status,
                        "rows": len(rows),
                        "new_observations": new_count,
                        "invalid_observations": len(invalid),
                    }
                )

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failed_days += 1
                elapsed = time.perf_counter() - t0
                print(
                    f"[{i:>3}/{total}] {target_date.isoformat()} "
                    f"FAILED  {type(exc).__name__}: {str(exc)[:180]} "
                    f"{elapsed:>5.1f}s",
                    flush=True,
                )
                results.append(
                    {
                        "date": target_date.isoformat(),
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:1000],
                    }
                )

            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

        if successful_days == 0:
            final_status = "FAILED"
        elif failed_days or total_invalid:
            final_status = "SUCCESS_WITH_INVALID"
        else:
            final_status = "SUCCESS"

        failed_detail = [
            f'{x["date"]}:{x.get("error_type", "ERROR")}'
            for x in results
            if x["status"] == "FAILED"
        ]

        run_row.update(
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": final_status,
                "records_downloaded": total_rows,
                "records_new": total_new,
                "records_invalid": total_invalid,
                "last_source_timestamp": last_success_date,
                "error_type": "PARTIAL_FAILURE" if failed_days else None,
                "error_message": "; ".join(failed_detail)[:1000] if failed_detail else None,
            }
        )
        store.insert_source_run(run_row)

        report = {
            "run_id": run_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "business_days_requested": len(days),
            "successful_days": successful_days,
            "no_data_days": no_data_days,
            "failed_days": failed_days,
            "secondary_rows": total_rows,
            "new_observations": total_new,
            "invalid_observations": total_invalid,
            "storage_backend": "postgres"
            if os.getenv("DATABASE_URL", "").strip()
            else "sqlite",
            "results": results,
        }

        report_dir = Path("data/backfill")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / (
            f"hnx_secondary_{start_date.isoformat()}_{end_date.isoformat()}.json"
        )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary = {k: v for k, v in report.items() if k != "results"}
        summary["report_path"] = str(report_path)
        print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
        return report

    except KeyboardInterrupt:
        run_row.update(
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "FAILED",
                "records_downloaded": total_rows,
                "records_new": total_new,
                "records_invalid": total_invalid,
                "last_source_timestamp": last_success_date,
                "error_type": "KeyboardInterrupt",
                "error_message": "Backfill interrupted by user.",
            }
        )
        store.insert_source_run(run_row)
        print("\nBackfill interrupted. Already inserted observations remain committed.")
        raise
    finally:
        store.close()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fast HNX secondary-market historical backfill for risk-factor history."
    )
    p.add_argument("--start-date", required=True, type=date.fromisoformat)
    p.add_argument("--end-date", required=True, type=date.fromisoformat)
    p.add_argument("--sleep-ms", type=int, default=200)
    p.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")),
    )
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    args = p.parse_args()

    run(
        start_date=args.start_date,
        end_date=args.end_date,
        db_path=args.db,
        raw_root=args.raw_root,
        sleep_ms=max(args.sleep_ms, 0),
    )


if __name__ == "__main__":
    main()
