from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from src.reporting.daily_brief import build_daily_risk_brief
from src.storage.factory import create_store


def run(*, db_path: Path, output: Path | None = None) -> str:
    store = create_store(local_db_path=db_path)
    try:
        brief = build_daily_risk_brief(store)
    finally:
        store.close()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(brief, encoding="utf-8")
    return brief


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--output", type=Path)
    p.add_argument(
        "--print-brief",
        action="store_true",
        help="Also print the full brief to stdout. Disabled by default for Windows console compatibility.",
    )
    args = p.parse_args()
    output = args.output
    if output is None:
        stamp = datetime.now(timezone.utc).date().isoformat()
        output = Path("reports") / f"daily-risk-brief-{stamp}.md"
    brief = run(db_path=args.db, output=output)
    # Keep default stdout ASCII-only. Windows PowerShell may expose cp1252 when
    # stdout is redirected (for example through `| Out-Null`), which cannot
    # encode Vietnamese text. The UTF-8 report file remains the canonical output.
    print(f"Wrote report: {output}")
    if args.print_brief:
        import sys
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        print(brief)


if __name__ == "__main__":
    main()
