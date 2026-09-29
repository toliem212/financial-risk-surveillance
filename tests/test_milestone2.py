from pathlib import Path

from src.storage.factory import create_store
from src.storage.raw_archive import archive_html


def test_store_factory_falls_back_to_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = create_store(local_db_path=tmp_path / "x.db")
    try:
        assert store.counts()["market_observation"] == 0
    finally:
        store.close()


def test_raw_archive_is_content_addressed_local(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    from datetime import date

    a, h1 = archive_html("<html>same</html>", source="test", session_date=date(2026, 9, 29), local_root=tmp_path)
    b, h2 = archive_html("<html>same</html>", source="test", session_date=date(2026, 9, 29), local_root=tmp_path)
    assert h1 == h2
    assert a == b
    assert Path(a).exists()
