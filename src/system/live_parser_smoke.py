from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from src.ingestion.hnx_cbonds import (
    BOND_LIST_URL, DISCLOSURE_URL, ISSUER_LIST_URL, RATING_URL, TRADING_STATUS_URL,
    fetch_page as cbis_fetch_page, parse_bond_list, parse_disclosures, parse_issuer_list,
    parse_ratings, parse_trading_status,
)
from src.ingestion.hnx_gov import fetch_auctions, fetch_secondary_day, parse_auction_html, parse_secondary_html
from src.ingestion.sbv_macro import PAGES as SBV_MACRO_PAGES, fetch_page as sbv_macro_fetch_page, parse_page as parse_sbv_macro
from src.ingestion.sbv_omo import fetch_omo_html, parse_omo_html
from src.ingestion.vira import fetch_latest_articles, parse_article_html


def _row(source: str, fetch_ok: bool, parse_ok: bool, record_count: int | None = None, detail: str = '') -> dict:
    return {
        'source': source,
        'fetch_ok': bool(fetch_ok),
        'parse_ok': bool(parse_ok),
        'record_count': record_count,
        'detail': detail,
    }


def run_live_parser_smoke(*, hnx_date: date | None = None) -> dict:
    target = hnx_date or date.today()
    rows: list[dict] = []

    # SBV OMO
    try:
        html, _ = fetch_omo_html()
        try:
            parsed = parse_omo_html(html)
            rows.append(_row('SBV_OMO', True, True, len(parsed)))
        except Exception as exc:
            rows.append(_row('SBV_OMO', True, False, None, f'{type(exc).__name__}: {exc}'))
    except Exception as exc:
        rows.append(_row('SBV_OMO', False, False, None, f'{type(exc).__name__}: {exc}'))

    # HNX Government Bonds: empty secondary on a non-trading date is not necessarily a parser failure,
    # so we report parsed count without requiring it to be positive.
    try:
        html, _ = fetch_secondary_day(target)
        try:
            parsed = parse_secondary_html(html, target)
            rows.append(_row('HNX_GOV_SECONDARY', True, True, len(parsed), f'date={target}'))
        except Exception as exc:
            rows.append(_row('HNX_GOV_SECONDARY', True, False, None, f'{type(exc).__name__}: {exc}'))
    except Exception as exc:
        rows.append(_row('HNX_GOV_SECONDARY', False, False, None, f'{type(exc).__name__}: {exc}'))

    try:
        start = target - timedelta(days=14)
        html, _ = fetch_auctions(start, target)
        try:
            parsed = parse_auction_html(html)
            rows.append(_row('HNX_GOV_AUCTION', True, True, len(parsed), f'window={start}..{target}'))
        except Exception as exc:
            rows.append(_row('HNX_GOV_AUCTION', True, False, None, f'{type(exc).__name__}: {exc}'))
    except Exception as exc:
        rows.append(_row('HNX_GOV_AUCTION', False, False, None, f'{type(exc).__name__}: {exc}'))

    # HNX CBIS public pages
    cbis_checks = [
        ('CBIS_ISSUERS', ISSUER_LIST_URL, parse_issuer_list),
        ('CBIS_BONDS', BOND_LIST_URL, parse_bond_list),
        ('CBIS_RATINGS', RATING_URL, parse_ratings),
        ('CBIS_DISCLOSURES', DISCLOSURE_URL, parse_disclosures),
        ('CBIS_TRADING_STATUS', TRADING_STATUS_URL, parse_trading_status),
    ]
    for name, url, parser in cbis_checks:
        try:
            html, _ = cbis_fetch_page(url)
            try:
                parsed = parser(html)
                rows.append(_row(name, True, True, len(parsed)))
            except Exception as exc:
                rows.append(_row(name, True, False, None, f'{type(exc).__name__}: {exc}'))
        except Exception as exc:
            rows.append(_row(name, False, False, None, f'{type(exc).__name__}: {exc}'))

    # VIRA latest bulletin discovery + article parser
    try:
        articles, _ = fetch_latest_articles()
        if not articles:
            rows.append(_row('VIRA_LATEST', True, False, 0, 'No DAILY/WEEKLY article discovered from listing'))
        else:
            parsed_count = 0
            failures = []
            for url, html, fetched_at in articles:
                try:
                    try:
                        parse_article_html(html, url=url, fetched_at=fetched_at)
                    except TypeError as exc:
                        # Backward-compatible with injected/test parsers that predate fetched_at.
                        if "fetched_at" not in str(exc):
                            raise
                        parse_article_html(html, url=url)
                    parsed_count += 1
                except Exception as exc:
                    failures.append(f'{url}: {type(exc).__name__}: {exc}')
            rows.append(_row('VIRA_LATEST', True, not failures, parsed_count, '; '.join(failures)))
    except Exception as exc:
        rows.append(_row('VIRA_LATEST', False, False, None, f'{type(exc).__name__}: {exc}'))

    # Slow-moving macro pages are parser-smoked individually.
    for page_id in SBV_MACRO_PAGES:
        name = f'SBV_MACRO_{page_id.upper()}'
        try:
            html, _, _ = sbv_macro_fetch_page(page_id)
            try:
                parsed = parse_sbv_macro(html, page_id=page_id)
                rows.append(_row(name, True, True, len(parsed)))
            except Exception as exc:
                rows.append(_row(name, True, False, None, f'{type(exc).__name__}: {exc}'))
        except Exception as exc:
            rows.append(_row(name, False, False, None, f'{type(exc).__name__}: {exc}'))

    fetch_ok = sum(1 for r in rows if r['fetch_ok'])
    parse_ok = sum(1 for r in rows if r['parse_ok'])
    return {
        'ok': all(r['parse_ok'] for r in rows),
        'hnx_date': target.isoformat(),
        'fetch_ok_count': fetch_ok,
        'parse_ok_count': parse_ok,
        'total_checks': len(rows),
        'checks': rows,
        'note': 'This smoke test performs live fetch+parse only and does not write observations, events, raw archive or signals.',
    }


def main() -> None:
    p = argparse.ArgumentParser(description='Live, non-destructive fetch+parse smoke test for all public sources.')
    p.add_argument('--hnx-date', type=date.fromisoformat, default=None, help='YYYY-MM-DD; defaults to today.')
    args = p.parse_args()
    result = run_live_parser_smoke(hnx_date=args.hnx_date)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
