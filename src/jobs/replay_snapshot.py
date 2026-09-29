from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.replay.point_in_time import build_snapshot
from src.storage.factory import create_store


def main():
    parser = argparse.ArgumentParser(description="Build a point-in-time surveillance replay snapshot")
    parser.add_argument("--at", required=True, help="ISO-8601 replay cutoff, including timezone offset")
    parser.add_argument("--mode", choices=["SYSTEM_KNOWN", "SOURCE_AVAILABLE"], default="SYSTEM_KNOWN")
    parser.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    parser.add_argument("--thresholds", type=Path, default=Path("config/thresholds.json"))
    args = parser.parse_args()

    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8"))
    store = create_store(local_db_path=args.db)
    try:
        snap = build_snapshot(store, args.at, thresholds, mode=args.mode)
    finally:
        store.close()

    payload = {
        "cutoff": snap.cutoff,
        "mode": snap.mode,
        "domain_state": snap.domain_state,
        "observation_count": len(snap.observations),
        "event_count": len(snap.events),
        "recorded_signal_count": len(snap.recorded_signals),
        "reconstructed_signal_count": len(snap.reconstructed_signals),
        "timeline": snap.timeline[:25],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
