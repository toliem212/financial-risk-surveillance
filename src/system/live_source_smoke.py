from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from typing import Iterable

import requests

from src.common.http import enable_system_trust, resilient_session


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    required_text_any: tuple[str, ...] = ()


PROBES = (
    Probe('SBV_HOME', 'https://www.sbv.gov.vn/'),
    Probe('HNX_HOME', 'https://www.hnx.vn/'),
    Probe('HNX_CBIS', 'https://cbonds.hnx.vn/', ('trái phiếu', 'Trai phieu', 'CBIS')),
    Probe('VIRA_HOME', 'https://vira.org.vn/', ('VIRA', 'Kinh tế', 'kinh tế')),
)


def probe_sources(probes: Iterable[Probe] = PROBES, *, timeout: float = 20.0) -> dict:
    trust_backend = enable_system_trust()
    session = resilient_session(user_agent='Mozilla/5.0 FRS/1.0 public-source-health-check', retries=1)
    rows = []
    for p in probes:
        started = time.perf_counter()
        try:
            r = session.get(p.url, timeout=timeout, allow_redirects=True)
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            body = r.text[:250000] if r.text else ''
            text_ok = True if not p.required_text_any else any(x.lower() in body.lower() for x in p.required_text_any)
            rows.append({
                'name': p.name,
                'url': p.url,
                'status_code': r.status_code,
                'elapsed_ms': elapsed,
                'reachable': 200 <= r.status_code < 500,
                'content_check': text_ok,
                'final_url': r.url,
                'error': None,
            })
        except Exception as exc:
            rows.append({
                'name': p.name, 'url': p.url, 'status_code': None,
                'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
                'reachable': False, 'content_check': False, 'final_url': None,
                'error': f'{type(exc).__name__}: {exc}',
            })
    return {
        'ok': all(r['reachable'] for r in rows),
        'probes': rows,
        'tls_trust_backend': trust_backend,
        'note': 'Reachability is not a guarantee that every downstream parser/API endpoint is unchanged. HNX/CBIS failures on a local network are isolated and should also be re-tested from GitHub Actions/cloud.',
    }


def main() -> None:
    p = argparse.ArgumentParser(description='Non-destructive reachability smoke test for public sources.')
    p.add_argument('--timeout', type=float, default=20.0)
    args = p.parse_args()
    result = probe_sources(timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
