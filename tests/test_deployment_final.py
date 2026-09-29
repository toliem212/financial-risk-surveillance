from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.policy import AIPolicy
from src.system import cloud_bootstrap
from src.system.live_source_smoke import Probe, probe_sources


def test_ai_default_is_cost_sensitive_luna(monkeypatch):
    for key in [
        'AI_MODEL', 'AI_ENABLED', 'OPENAI_API_KEY', 'AI_DAILY_CALL_LIMIT',
        'AI_INPUT_USD_PER_MTOK', 'AI_CACHED_INPUT_USD_PER_MTOK', 'AI_OUTPUT_USD_PER_MTOK'
    ]:
        monkeypatch.delenv(key, raising=False)
    p = AIPolicy.from_env()
    assert p.model == 'gpt-5.6-luna'
    assert p.enabled is False


def test_cloud_bootstrap_dry_run_requires_config(monkeypatch, tmp_path):
    schema = tmp_path / 'schema.sql'
    schema.write_text('select 1;', encoding='utf-8')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-key')
    result = cloud_bootstrap.run_bootstrap(apply=False, schema_path=schema)
    assert result['status'] == 'DRY_RUN'
    assert result['apply'] is False


def test_cloud_bootstrap_missing_env(monkeypatch, tmp_path):
    schema = tmp_path / 'schema.sql'
    schema.write_text('select 1;', encoding='utf-8')
    for key in ['DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY']:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError):
        cloud_bootstrap.run_bootstrap(apply=False, schema_path=schema)


def test_live_source_smoke_is_non_destructive(monkeypatch):
    class Resp:
        status_code = 200
        text = '<html>hello market</html>'
        url = 'https://example.test/final'

    class Session:
        def __init__(self):
            self.headers = {}
        def get(self, *args, **kwargs):
            return Resp()

    monkeypatch.setattr('src.system.live_source_smoke.requests.Session', Session)
    result = probe_sources([Probe('X', 'https://example.test', ('hello',))], timeout=1)
    assert result['ok'] is True
    assert result['probes'][0]['content_check'] is True


def test_live_parser_smoke_with_fakes(monkeypatch):
    from datetime import date, datetime, timezone
    import src.system.live_parser_smoke as m

    monkeypatch.setattr(m, 'fetch_omo_html', lambda: ('omo', datetime.now(timezone.utc)))
    monkeypatch.setattr(m, 'parse_omo_html', lambda html: [1])
    monkeypatch.setattr(m, 'fetch_secondary_day', lambda d: ('sec', datetime.now(timezone.utc)))
    monkeypatch.setattr(m, 'parse_secondary_html', lambda html, d: [])
    monkeypatch.setattr(m, 'fetch_auctions', lambda a, b: ('auc', datetime.now(timezone.utc)))
    monkeypatch.setattr(m, 'parse_auction_html', lambda html: [1, 2])
    monkeypatch.setattr(m, 'cbis_fetch_page', lambda url: ('cbis', datetime.now(timezone.utc)))
    monkeypatch.setattr(m, 'parse_issuer_list', lambda html: [1])
    monkeypatch.setattr(m, 'parse_bond_list', lambda html: [1])
    monkeypatch.setattr(m, 'parse_ratings', lambda html: [1])
    monkeypatch.setattr(m, 'parse_disclosures', lambda html: [1])
    monkeypatch.setattr(m, 'parse_trading_status', lambda html: [1])
    monkeypatch.setattr(m, 'fetch_latest_articles', lambda: ([('u', 'v', datetime.now(timezone.utc))], datetime.now(timezone.utc)))
    monkeypatch.setattr(m, 'parse_article_html', lambda html, url='': object())
    monkeypatch.setattr(m, 'sbv_macro_fetch_page', lambda page_id: ('macro', datetime.now(timezone.utc), 'u'))
    monkeypatch.setattr(m, 'parse_sbv_macro', lambda html, page_id='': [1])

    result = m.run_live_parser_smoke(hnx_date=date(2026, 9, 29))
    assert result['ok'] is True
    assert result['parse_ok_count'] == result['total_checks']
    assert result['total_checks'] >= 10


def test_daily_brief_cli_default_stdout_is_ascii_safe(tmp_path, monkeypatch, capsys):
    """Default CLI output must not print Vietnamese brief text to cp1252-like consoles."""
    from src.jobs import generate_daily_brief as mod

    report = tmp_path / "brief.md"
    monkeypatch.setattr(mod, "run", lambda **kwargs: "Bản tin rủi ro ngày – kiểm thử tiếng Việt")
    monkeypatch.setattr(
        "sys.argv",
        ["generate_daily_brief", "--db", str(tmp_path / "demo.db"), "--output", str(report)],
    )
    mod.main()
    out = capsys.readouterr().out
    assert "Wrote report:" in out
    assert "Bản tin" not in out
