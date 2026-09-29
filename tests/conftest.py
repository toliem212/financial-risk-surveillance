from __future__ import annotations

import pytest

import src.config.env as env_mod


@pytest.fixture(autouse=True)
def isolate_tests_from_local_dotenv(monkeypatch):
    for key in (
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    # Prevent create_store() from loading the developer's real .env during tests.
    # Tests that specifically test load_dotenv() reset this flag themselves.
    monkeypatch.setattr(env_mod, "_LOADED", True)
