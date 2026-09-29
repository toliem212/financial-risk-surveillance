from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.ai.client import AIService
from src.ai.disclosure import classify_disclosure
from src.ai.policy import AIPolicy
from src.storage.factory import create_store


def main():
    p = argparse.ArgumentParser(description="Optional AI classification for one CBIS disclosure. Does not overwrite deterministic events.")
    p.add_argument("--title", required=True)
    p.add_argument("--text-file", type=Path)
    p.add_argument("--issuer", default="")
    p.add_argument("--source-url", default="")
    p.add_argument("--db", type=Path, default=Path("data/local/surveillance.db"))
    args = p.parse_args()

    body = args.text_file.read_text(encoding="utf-8") if args.text_file else ""
    store = create_store(local_db_path=args.db)
    try:
        service = AIService(store, policy=AIPolicy.from_env())
        result = classify_disclosure(
            service, title=args.title, body_text=body,
            issuer_name=args.issuer, source_url=args.source_url,
        )
        print(json.dumps({
            "cached": result.cached,
            "model": result.model,
            "tokens": result.total_tokens,
            "result": result.data,
        }, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
