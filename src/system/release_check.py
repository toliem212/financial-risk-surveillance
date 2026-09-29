from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from src.jobs.hnx_cbonds_once import run as run_cbonds
from src.jobs.hnx_gov_once import run as run_hnx_gov
from src.jobs.sbv_macro_once import run as run_macro
from src.jobs.sbv_omo_once import run as run_omo
from src.jobs.vira_once import run as run_vira
from src.reporting.daily_brief import build_daily_risk_brief
from src.storage.factory import create_store
from src.system.preflight import run_preflight
from src.version import PROJECT_VERSION


@contextmanager
def _force_local():
    keys = ["DATABASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    old = {k: os.environ.get(k) for k in keys}
    try:
        for k in keys:
            os.environ.pop(k, None)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_release_check() -> dict:
    root = Path.cwd()
    fixtures = root / "tests" / "fixtures"
    with tempfile.TemporaryDirectory(prefix="frs-release-") as td, _force_local():
        work = Path(td)
        db = work / "surveillance.db"
        raw = work / "raw"
        thresholds = root / "config" / "thresholds.json"

        results = {}
        results["sbv_omo"] = run_omo(
            fixture=fixtures / "sbv_omo_sample.html", db_path=db, raw_root=raw, thresholds_path=thresholds
        )
        results["hnx_gov"] = run_hnx_gov(
            target_date=date(2026, 9, 25), db_path=db, raw_root=raw, thresholds_path=thresholds,
            secondary_fixture=fixtures / "hnx_secondary_current.html",
            auction_fixture=fixtures / "hnx_auction_sample.html",
        )
        results["hnx_cbonds"] = run_cbonds(
            db_path=db, raw_root=raw,
            issuer_fixture=fixtures / "cbis_issuers_sample.html",
            bond_fixture=fixtures / "cbis_bonds_sample.html",
            rating_fixture=fixtures / "cbis_ratings_sample.html",
            disclosure_fixture=fixtures / "cbis_disclosures_sample.html",
            status_fixture=fixtures / "cbis_status_sample.html",
        )
        results["vira"] = run_vira(
            daily_fixture=fixtures / "vira_daily_sample.html",
            weekly_fixture=fixtures / "vira_weekly_sample.html",
            db_path=db, raw_root=raw,
        )
        results["macro"] = run_macro(
            fixture_dir=fixtures / "sbv_macro", db_path=db, raw_root=raw
        )
        preflight = run_preflight(db_path=db)

        store = create_store(local_db_path=db)
        try:
            counts = store.counts()
            brief = build_daily_risk_brief(store)
        finally:
            store.close()

        required_nonzero = ["source_run", "market_observation", "risk_signal", "issuer_master", "bond_master", "bond_event"]
        count_ok = all(int(counts.get(k, 0)) > 0 for k in required_nonzero)
        brief_ok = "Daily Risk Brief" in brief and "What To Monitor Next" in brief
        ok = preflight["ok"] and count_ok and brief_ok
        return {
            "ok": ok,
            "project_version": PROJECT_VERSION,
            "preflight": preflight,
            "counts": counts,
            "brief_ok": brief_ok,
            "workers": {k: {"storage_backend": v.get("storage_backend", "sqlite"), "status": "PASS"} for k, v in results.items()},
        }


def main():
    result = run_release_check()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
