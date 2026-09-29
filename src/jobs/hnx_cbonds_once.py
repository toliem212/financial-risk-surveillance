from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.version import PROJECT_VERSION
from src.ingestion.hnx_cbonds import (
    BOND_LIST_URL, DISCLOSURE_URL, ISSUER_LIST_URL, PARSER_VERSION, RATING_URL, TRADING_STATUS_URL, IssuerRecord,
    fetch_page, parse_bond_list, parse_disclosures, parse_issuer_list, parse_ratings, parse_trading_status,
)
from src.normalization.hnx_cbonds import (
    bonds_to_rows, disclosures_to_events, issuers_to_rows, ratings_to_events, trading_status_to_events,
)
from src.signals.corporate_bond import event_signals
from src.storage.factory import create_store
from src.storage.raw_archive import archive_html

CODE_VERSION = PROJECT_VERSION


def _load(url: str, fixture: Path | None):
    if fixture:
        return fixture.read_text(encoding="utf-8"), datetime.now(timezone.utc)
    return fetch_page(url)


def run(*, db_path: Path, raw_root: Path, issuer_fixture: Path | None = None,
        bond_fixture: Path | None = None, rating_fixture: Path | None = None,
        disclosure_fixture: Path | None = None, status_fixture: Path | None = None) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    store = create_store(local_db_path=db_path)
    run_row = {
        "run_id": run_id, "source": "HNX_CBIS", "worker": "hnx_cbonds_once",
        "started_at": started.isoformat(), "finished_at": None, "status": "RUNNING",
        "records_downloaded": 0, "records_new": 0, "records_changed": 0,
        "records_invalid": 0, "last_source_timestamp": None, "error_type": None,
        "error_message": None, "code_version": CODE_VERSION, "parser_version": PARSER_VERSION,
    }
    store.insert_source_run(run_row)
    try:
        pages = {}
        specs = {
            "issuers": (ISSUER_LIST_URL, issuer_fixture),
            "bonds": (BOND_LIST_URL, bond_fixture),
            "ratings": (RATING_URL, rating_fixture),
            "disclosures": (DISCLOSURE_URL, disclosure_fixture),
            "trading_status": (TRADING_STATUS_URL, status_fixture),
        }
        fetched_at = started
        for key, (url, fixture) in specs.items():
            html, ft = _load(url, fixture)
            fetched_at = max(fetched_at, ft)
            raw_path, _ = archive_html(html, source=f"hnx_cbonds_{key}", session_date=ft.date(), local_root=raw_root)
            pages[key] = (html, raw_path)

        issuer_records = parse_issuer_list(pages["issuers"][0])
        bond_records = parse_bond_list(pages["bonds"][0])
        rating_records = parse_ratings(pages["ratings"][0])
        disclosure_records = parse_disclosures(pages["disclosures"][0])
        status_records = parse_trading_status(pages["trading_status"][0])

        # The public issuer page is paginated, while latest events may reference issuers not
        # visible on its first page. Seed minimal issuer identities from every parsed source,
        # then let richer issuer-list records overwrite them before DB upsert.
        issuer_names = {r.issuer_name for r in bond_records}
        issuer_names.update(r.issuer_name for r in rating_records)
        issuer_names.update(r.issuer_name for r in disclosure_records)
        issuer_names.update(r.issuer_name for r in status_records)
        minimal = [IssuerRecord(None, name, None, None, None, None, None) for name in issuer_names]
        issuer_rows = {r["issuer_id"]: r for r in issuers_to_rows(minimal, fetched_at)}
        for r in issuers_to_rows(issuer_records, fetched_at):
            issuer_rows[r["issuer_id"]] = r
        issuers = list(issuer_rows.values())
        bonds = bonds_to_rows(bond_records, fetched_at)
        events = (
            ratings_to_events(rating_records, fetched_at)
            + disclosures_to_events(disclosure_records, fetched_at)
            + trading_status_to_events(status_records, fetched_at)
        )

        new_issuers = store.upsert_issuers(issuers)
        new_bonds = store.upsert_bonds(bonds)
        new_events = store.insert_bond_events(events)
        signals = event_signals(events)
        new_signals = store.insert_signals(signals)

        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(), "status": "SUCCESS",
            "records_downloaded": len(issuer_records) + len(bond_records) + len(rating_records) + len(disclosure_records) + len(status_records),
            "records_new": new_issuers + new_bonds + new_events + new_signals,
            "last_source_timestamp": fetched_at.isoformat(),
        })
        store.insert_source_run(run_row)
        return {
            "run_id": run_id, "issuers": len(issuer_records), "bonds": len(bond_records),
            "ratings": len(rating_records), "disclosures": len(disclosure_records),
            "trading_status": len(status_records), "events": len(events), "signals": len(signals),
            "inserted": {"issuers": new_issuers, "bonds": new_bonds, "events": new_events, "signals": new_signals},
        }
    except Exception as exc:
        run_row.update({
            "finished_at": datetime.now(timezone.utc).isoformat(), "status": "FAILED",
            "error_type": type(exc).__name__, "error_message": str(exc),
        })
        store.insert_source_run(run_row)
        raise
    finally:
        store.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=Path("data/local/surveillance.db"))
    p.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    p.add_argument("--issuer-fixture", type=Path)
    p.add_argument("--bond-fixture", type=Path)
    p.add_argument("--rating-fixture", type=Path)
    p.add_argument("--disclosure-fixture", type=Path)
    p.add_argument("--status-fixture", type=Path)
    args = p.parse_args()
    print(json.dumps(run(db_path=args.db, raw_root=args.raw_root,
        issuer_fixture=args.issuer_fixture, bond_fixture=args.bond_fixture, rating_fixture=args.rating_fixture,
        disclosure_fixture=args.disclosure_fixture, status_fixture=args.status_fixture), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
