from __future__ import annotations

import os
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@lru_cache(maxsize=1)
def enable_system_trust() -> str:
    """Use the operating-system certificate store when truststore is available.

    This is especially useful on Windows, where browsers may trust a certificate
    chain that certifi (used by Requests by default) cannot build. Certificate
    verification remains enabled; this function does NOT disable TLS checks.
    """
    if os.getenv("FRS_USE_SYSTEM_TRUST", "1").strip().lower() in {"0", "false", "no"}:
        return "certifi"
    try:
        import truststore  # type: ignore

        truststore.inject_into_ssl()
        return "system"
    except Exception:
        return "certifi"


def resilient_session(*, user_agent: str, retries: int = 2) -> requests.Session:
    enable_system_trust()
    retry = Retry(
        total=retries,
        connect=retries,
        read=1,
        status=retries,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s = requests.Session()
    if hasattr(s, "mount"):
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return s
