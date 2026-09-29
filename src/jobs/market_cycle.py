from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.jobs.hnx_cbonds_once import run as run_cbonds
from src.jobs.hnx_gov_once import run as run_hnx_gov
from src.jobs.sbv_omo_once import run as run_omo


def run_cycle(*, db_path: Path, raw_root: Path, thresholds_path: Path, strict: bool = False) -> dict:
    target_date = datetime.now(ZoneInfo("Asia/Bangkok")).date()
    tasks = [
        (
            "sbv_omo",
            lambda: run_omo(fixture=None, db_path=db_path, raw_root=raw_root, thresholds_path=thresholds_path),
        ),
        (
            "hnx_gov",
            lambda: run_hnx_gov(
                target_date=target_date,
                db_path=db_path,
                raw_root=raw_root,
                thresholds_path=thresholds_path,
            ),
        ),
        (
            "hnx_cbonds",
            lambda: run_cbonds(db_path=db_path, raw_root=raw_root),
        ),
    ]

    result: dict[str, dict] = {}
    success = 0
    for name, fn in tasks:
        try:
            payload = fn()
            result[name] = {"status": "SUCCESS", "result": payload}
            success += 1
        except Exception as exc:
            result[name] = {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            }

    failure_count = len(tasks) - success
    status = "FAILED" if success == 0 else ("DEGRADED" if failure_count else "SUCCESS")
    summary = {
        "status": status,
        "target_date": target_date.isoformat(),
        "success_count": success,
        "failure_count": failure_count,
        "unavailable_sources": [name for name, payload in result.items() if payload.get("status") == "FAILED"],
        "sources": result,
        "note": "A failed source is unavailable/missing data, never a zero market value.",
    }
    if success == 0 or (strict and success != len(tasks)):
        raise RuntimeError(json.dumps(summary, ensure_ascii=False))
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--thresholds", type=Path, default=Path("config/thresholds.json"))
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    print(json.dumps(run_cycle(db_path=args.db, raw_root=args.raw_root, thresholds_path=args.thresholds, strict=args.strict), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
