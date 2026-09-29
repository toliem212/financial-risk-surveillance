from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def archive_html(content: str, *, source: str, session_date: date, local_root: Path) -> tuple[str, str]:
    """Archive raw HTML locally or in Supabase Storage when configured.

    Returns (raw_object_id, sha256). The content-addressed object path makes writes idempotent.
    """
    digest = _digest(content)
    object_path = f"{source}/{session_date.isoformat()}/{digest}.html"

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    bucket = os.getenv("SUPABASE_RAW_BUCKET", "raw-market-data").strip()

    if supabase_url and service_key:
        from supabase import create_client

        client = create_client(supabase_url, service_key)
        try:
            client.storage.from_(bucket).upload(
                path=object_path,
                file=content.encode("utf-8"),
                file_options={"content-type": "text/html; charset=utf-8", "upsert": "false"},
            )
        except Exception as exc:
            # Content-addressed path: an existing object means the archive is already present.
            msg = str(exc).lower()
            if "already exists" not in msg and "duplicate" not in msg and "409" not in msg:
                raise
        return f"supabase://{bucket}/{object_path}", digest

    folder = local_root / source / session_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.html"
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return str(path), digest
