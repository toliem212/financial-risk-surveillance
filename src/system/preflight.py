from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.ai.policy import AIPolicy
from src.storage.factory import create_store
from src.version import PROJECT_VERSION, SCHEMA_VERSION


def _check(name: str, ok: bool, detail: str, required: bool = True) -> dict:
    return {"name": name, "ok": bool(ok), "required": required, "detail": detail}


def run_preflight(*, db_path: Path, write_meta: bool = True, require_postgres: bool = False, require_cloud_raw: bool = False) -> dict:
    checks: list[dict] = []
    checks.append(_check("Python", sys.version_info >= (3, 11), platform.python_version()))
    for path in ["config/thresholds.json", "schema/postgres.sql", "app/Home.py"]:
        checks.append(_check(f"File {path}", Path(path).exists(), "present" if Path(path).exists() else "missing"))

    # Configuration consistency.
    sb_url = os.getenv("SUPABASE_URL", "").strip()
    sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    checks.append(_check(
        "Supabase raw archive configuration",
        bool(sb_url) == bool(sb_key),
        "configured" if sb_url and sb_key else "local raw archive fallback",
        required=False,
    ))

    policy = AIPolicy.from_env()
    if policy.enabled:
        checks.append(_check("OpenAI API key", bool(os.getenv("OPENAI_API_KEY", "").strip()), "AI enabled", required=True))
    else:
        checks.append(_check("AI opt-in", True, "AI disabled; deterministic core only", required=False))

    backend = "postgres" if os.getenv("DATABASE_URL", "").strip() else "sqlite"
    if require_postgres:
        checks.append(_check("Production database backend", backend == "postgres", f"required=postgres, current={backend}"))
    if require_cloud_raw:
        checks.append(_check("Persistent raw archive", bool(sb_url and sb_key), "Supabase Storage configured" if sb_url and sb_key else "missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY"))
    store = None
    try:
        store = create_store(local_db_path=db_path)
        counts = store.counts()
        checks.append(_check("Database connection", True, backend))
        expected = {"source_run", "market_observation", "risk_signal", "issuer_master", "bond_master", "bond_event", "investigation_case", "investigation_audit", "ai_cache", "ai_usage_log", "project_meta"}
        missing = sorted(expected - set(counts))
        checks.append(_check("Database schema", not missing, "ok" if not missing else f"missing: {', '.join(missing)}"))
        if write_meta and not missing:
            now = datetime.now(timezone.utc).isoformat()
            store.set_project_meta("schema_version", SCHEMA_VERSION, now)
            store.set_project_meta("project_version", PROJECT_VERSION, now)
            counts = store.counts()
        try:
            schema = store.get_project_meta("schema_version")
            got = str(schema.get("value")) if schema else None
            checks.append(_check("Schema version", got == SCHEMA_VERSION, f"expected {SCHEMA_VERSION}, got {got}"))
        except Exception as exc:
            checks.append(_check("Schema version", False, f"{type(exc).__name__}: {exc}"))
    except Exception as exc:
        counts = {}
        checks.append(_check("Database connection", False, f"{type(exc).__name__}: {exc}"))
    finally:
        if store is not None:
            store.close()

    required_failures = [c for c in checks if c["required"] and not c["ok"]]
    return {
        "project_version": PROJECT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "backend": backend,
        "ok": not required_failures,
        "checks": checks,
        "counts": counts,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path(os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db")))
    p.add_argument("--no-write-meta", action="store_true")
    p.add_argument("--require-postgres", action="store_true")
    p.add_argument("--require-cloud-raw", action="store_true")
    args = p.parse_args()
    result = run_preflight(
        db_path=args.db, write_meta=not args.no_write_meta,
        require_postgres=args.require_postgres, require_cloud_raw=args.require_cloud_raw,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
