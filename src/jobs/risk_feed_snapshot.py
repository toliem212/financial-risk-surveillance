from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.investigation.risk_feed import build_investigation_case, build_risk_feed
from src.storage.factory import create_store


def main():
    p = argparse.ArgumentParser(description="Print the current cross-market risk feed or one investigation case as JSON.")
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--signal-id")
    args = p.parse_args()

    store = create_store(local_db_path=args.db)
    try:
        if args.signal_id:
            case = build_investigation_case(store, args.signal_id)
            payload = {
                "signal": case.signal,
                "evidence": case.evidence,
                "data_quality": case.data_quality,
                "historical_context": case.historical_context,
                "related_observations": case.related_observations,
                "possible_risk_transmission": case.possible_risk_transmission,
                "monitor_next": case.monitor_next,
            }
        else:
            payload = build_risk_feed(store, limit=args.limit)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    finally:
        store.close()


if __name__ == "__main__":
    main()
