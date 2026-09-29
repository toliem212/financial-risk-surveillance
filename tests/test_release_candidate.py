import os
from pathlib import Path

from src.ingestion.sbv_macro import parse_page
from src.jobs.sbv_macro_once import run as run_macro
from src.storage.sqlite_store import SQLiteStore


def test_sbv_macro_parser_keeps_vietnamese_numbers_and_dot_decimal():
    root = Path("tests/fixtures/sbv_macro")
    m2 = parse_page((root / "m2.html").read_text(encoding="utf-8"), page_id="m2")
    assert m2[0].level == 18123456.7
    assert m2[0].growth_ytd_pct == 8.25
    assert m2[1].growth_ytd_pct == 9.15


def test_sbv_macro_ldr_is_percentage_snapshot():
    root = Path("tests/fixtures/sbv_macro")
    rows = parse_page((root / "ldr.html").read_text(encoding="utf-8"), page_id="ldr")
    assert rows[0].level == 78.35


def test_sbv_macro_job_is_idempotent(tmp_path):
    db = tmp_path / "surveillance.db"
    raw = tmp_path / "raw"
    fixtures = Path("tests/fixtures/sbv_macro")
    first = run_macro(fixture_dir=fixtures, db_path=db, raw_root=raw)
    second = run_macro(fixture_dir=fixtures, db_path=db, raw_root=raw)
    assert first["new_observations"] > 0
    assert second["new_observations"] == 0
    store = SQLiteStore(db)
    try:
        obs = store.recent_observations(source="SBV", limit=100)
        macro = [x for x in obs if str(x["metric_id"]).startswith("SBV.MACRO.")]
        assert macro
        assert any(x["measure_type"] == "STOCK" for x in macro)
        assert any(x["measure_type"] == "SNAPSHOT" for x in macro)
    finally:
        store.close()

from src.reporting.daily_brief import build_daily_risk_brief


def test_daily_brief_generates_without_ai(tmp_path):
    db = tmp_path / "surveillance.db"
    raw = tmp_path / "raw"
    fixtures = Path("tests/fixtures/sbv_macro")
    run_macro(fixture_dir=fixtures, db_path=db, raw_root=raw)
    store = SQLiteStore(db)
    try:
        brief = build_daily_risk_brief(store)
        assert "Daily Risk Brief" in brief
        assert "Structural Macro Context" in brief
        assert "M2 total" in brief
        assert "What To Monitor Next" in brief
    finally:
        store.close()

from src.system.preflight import run_preflight


def test_preflight_passes_on_local_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AI_ENABLED", raising=False)
    result = run_preflight(db_path=tmp_path / "preflight.db")
    assert result["ok"] is True
    assert result["backend"] == "sqlite"
    assert result["counts"]["project_meta"] >= 0

from src.system.release_check import run_release_check


def test_release_check_end_to_end():
    result = run_release_check()
    assert result["ok"] is True
    assert result["brief_ok"] is True
    assert result["counts"]["market_observation"] > 0


def test_preflight_can_require_postgres(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = run_preflight(db_path=tmp_path / "preflight.db", require_postgres=True)
    assert result["ok"] is False
    assert any(c["name"] == "Production database backend" and not c["ok"] for c in result["checks"])

from src.config.env import load_dotenv


def test_dotenv_loader_does_not_override_existing(tmp_path, monkeypatch):
    import src.config.env as env_mod
    env_mod._LOADED = False
    p = tmp_path / ".env"
    p.write_text("X_TEST=from_file\nY_TEST='quoted'\n", encoding="utf-8")
    monkeypatch.setenv("X_TEST", "existing")
    monkeypatch.delenv("Y_TEST", raising=False)
    load_dotenv(p)
    assert os.environ["X_TEST"] == "existing"
    assert os.environ["Y_TEST"] == "quoted"
    env_mod._LOADED = False


def test_vira_accepts_reversed_publication_timestamp():
    from src.ingestion.vira import parse_article_html

    html = '''
    <html><body>
      <h1>Bản tin Kinh tế - Tài chính ngày 25/09/2026</h1>
      <div>25/09/2026 07:59</div>
      <div class="detail-news-content">Thị trường ngoại tệ: Phiên 24/09, NHNN niêm yết tỷ giá trung tâm ở mức 25.600 VND/USD.</div>
    </body></html>
    '''
    article = parse_article_html(html, url="fixture://vira/reversed")
    assert article.article_date.isoformat().startswith("2026-09-25T07:59")
    assert article.publication_time_inferred is False
    assert article.market_date.isoformat() == "2026-09-24"


def test_vira_missing_publication_time_uses_conservative_first_observed_fallback():
    from datetime import datetime, timezone
    from src.ingestion.vira import parse_article_html

    html = '''
    <html><body>
      <h1>Bản tin Kinh tế - Tài chính ngày 25/09/2026</h1>
      <div class="detail-news-content">Thị trường ngoại tệ: Phiên 24/09, NHNN niêm yết tỷ giá trung tâm ở mức 25.600 VND/USD.</div>
    </body></html>
    '''
    fetched = datetime(2026, 9, 25, 2, 15, tzinfo=timezone.utc)
    article = parse_article_html(html, url="fixture://vira/fallback", fetched_at=fetched)
    assert article.publication_time_inferred is True
    assert article.article_date.astimezone(timezone.utc) == fetched
