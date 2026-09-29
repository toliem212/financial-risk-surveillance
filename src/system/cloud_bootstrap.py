from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


from src.config.env import load_dotenv
from src.version import PROJECT_VERSION, SCHEMA_VERSION


def _require_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Missing required environment variable: {name}')
    return value


def apply_postgres_schema(database_url: str, schema_path: Path) -> None:
    import psycopg
    sql = schema_path.read_text(encoding='utf-8')
    # prepare_threshold=None is required for compatibility with Supabase transaction pooler.
    statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
    with psycopg.connect(database_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt, prepare=False)
        conn.commit()


def ensure_storage_bucket(supabase_url: str, service_role_key: str, bucket: str) -> str:
    from supabase import create_client

    client = create_client(supabase_url, service_role_key)
    try:
        client.storage.get_bucket(bucket)
        return 'EXISTS'
    except Exception:
        client.storage.create_bucket(bucket, options={'public': False})
        return 'CREATED'


def run_bootstrap(*, apply: bool = False, schema_path: Path = Path('schema/postgres.sql')) -> dict:
    load_dotenv()
    database_url = _require_env('DATABASE_URL')
    supabase_url = _require_env('SUPABASE_URL')
    service_key = _require_env('SUPABASE_SERVICE_ROLE_KEY')
    bucket = os.getenv('SUPABASE_RAW_BUCKET', 'raw-market-data').strip() or 'raw-market-data'

    result = {
        'project_version': PROJECT_VERSION,
        'schema_version': SCHEMA_VERSION,
        'schema_path': str(schema_path),
        'bucket': bucket,
        'apply': apply,
    }
    if not schema_path.exists():
        raise FileNotFoundError(schema_path)

    if not apply:
        result['status'] = 'DRY_RUN'
        result['next'] = 'Re-run with --apply to execute idempotent schema DDL and ensure the Storage bucket.'
        return result

    apply_postgres_schema(database_url, schema_path)
    result['database_schema'] = 'APPLIED'
    result['storage_bucket'] = ensure_storage_bucket(supabase_url, service_key, bucket)
    result['status'] = 'OK'
    return result


def main() -> None:
    p = argparse.ArgumentParser(description='Idempotently bootstrap Supabase/PostgreSQL for FRS.')
    p.add_argument('--apply', action='store_true', help='Actually execute DDL and create/check the raw Storage bucket.')
    p.add_argument('--schema', type=Path, default=Path('schema/postgres.sql'))
    args = p.parse_args()
    try:
        result = run_bootstrap(apply=args.apply, schema_path=args.schema)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({'status': 'FAILED', 'error_type': type(exc).__name__, 'error': str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
