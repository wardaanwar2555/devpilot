import pytest

from app.services import store


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'test.db'}")
    for var in ("LLM_API_KEY", "DEVPILOT_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("RATE_LIMIT_PER_HOUR", "1000")
    store._session_factory.cache_clear()
    yield
    store._session_factory.cache_clear()
