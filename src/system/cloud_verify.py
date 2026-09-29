from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.config.env import load_dotenv
from src.storage.factory import create_store
from src.version import PROJECT_VERSION, SCHEMA_VERSION


def _check(name: str, ok: bool, detail: str) -> dict:
    return {'name': name, 'ok': bool(ok), 'detail': detail}


def _storage_verify(*, write_test: bool = False) -> list[dict]:
    url = os.getenv('SUPABASE_URL', '').strip()
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    bucket = os.getenv('SUPABASE_RAW_BUCKET', 'raw-market-data').strip() or 'raw-market-data'
    if not url or not key:
        return [_check('Supabase Storage credentials', False, 'SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing')]

    from supabase import create_client
    client = create_client(url, key)
    checks: list[dict] = []
    try:
        b = client.storage.get_bucket(bucket)
        checks.append(_check('Supabase Storage bucket', True, f'{bucket} reachable'))
    except Exception as exc:
        return [_check('Supabase Storage bucket', False, f'{type(exc).__name__}: {exc}')]

    if write_test:
        path = f'_health/{uuid.uuid4()}.txt'
        payload = f'FRS cloud verify {datetime.now(timezone.utc).isoformat()}'.encode('utf-8')
        try:
            client.storage.from_(bucket).upload(path=path, file=payload, file_options={'content-type': 'text/plain', 'upsert': 'false'})
            client.storage.from_(bucket).remove([path])
            checks.append(_check('Supabase Storage write/delete', True, 'sentinel upload/delete succeeded'))
        except Exception as exc:
            checks.append(_check('Supabase Storage write/delete', False, f'{type(exc).__name__}: {exc}'))
    return checks


def run_cloud_verify(*, write_test: bool = False) -> dict:
    load_dotenv()
    checks: list[dict] = []
    backend = 'postgres' if os.getenv('DATABASE_URL', '').strip() else 'sqlite'
    checks.append(_check('Database backend', backend == 'postgres', f'current={backend}'))

    counts = {}
    store = None
    try:
        store = create_store(local_db_path=Path('data/local/surveillance.db'))
        counts = store.counts()
        checks.append(_check('PostgreSQL connection', backend == 'postgres', f'{len(counts)} tables visible'))
        meta = store.get_project_meta('schema_version')
        got = str(meta.get('value')) if meta else None
        checks.append(_check('Schema version', got == SCHEMA_VERSION, f'expected={SCHEMA_VERSION}, got={got}'))
    except Exception as exc:
        checks.append(_check('PostgreSQL connection', False, f'{type(exc).__name__}: {exc}'))
    finally:
        if store is not None:
            store.close()

    checks.extend(_storage_verify(write_test=write_test))
    ok = all(c['ok'] for c in checks)
    return {
        'ok': ok,
        'project_version': PROJECT_VERSION,
        'schema_version': SCHEMA_VERSION,
        'checks': checks,
        'counts': counts,
    }


def main() -> None:
    p = argparse.ArgumentParser(description='Verify live Supabase database and Storage connectivity.')
    p.add_argument('--write-test', action='store_true', help='Upload then delete a tiny sentinel object from raw Storage.')
    args = p.parse_args()
    result = run_cloud_verify(write_test=args.write_test)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
