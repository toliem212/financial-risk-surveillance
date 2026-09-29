from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def load_dotenv(path: str | Path = ".env") -> None:
    """Tiny dependency-free .env loader.

    Existing environment variables always win. Supports simple KEY=VALUE lines and
    optional matching single/double quotes; intentionally ignores shell expansion.
    """
    global _LOADED
    if _LOADED:
        return
    p = Path(path)
    if not p.exists():
        _LOADED = True
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    _LOADED = True
