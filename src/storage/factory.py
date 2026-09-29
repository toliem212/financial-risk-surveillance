from __future__ import annotations

import os
from pathlib import Path

from src.storage.sqlite_store import SQLiteStore
from src.config.env import load_dotenv


def create_store(*, local_db_path: str | Path | None = None):
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        from src.storage.postgres_store import PostgresStore
        return PostgresStore(database_url)

    path = Path(local_db_path or os.getenv("LOCAL_DB_PATH", "data/local/surveillance.db"))
    return SQLiteStore(path)
