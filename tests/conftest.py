"""
Shared test fixtures. Every test gets a fresh, isolated SQLite database (a
temp file, not your real storage/jobhunter.db) via a FastAPI dependency
override, and a TestClient with auth pre-configured.

Note: app.main / app.models are imported once per test session (normal
Python module caching) since SQLModel's declarative registry doesn't
support being re-defined against the same class names on re-import. That's
fine -- isolation between tests comes from swapping the database engine via
`get_session`, not from reimporting the app.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key-123")
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ADZUNA_APP_ID", "")
    monkeypatch.setenv("ADZUNA_APP_KEY", "")
    monkeypatch.setenv("JOOBLE_API_KEY", "")
    monkeypatch.setenv("SERPAPI_KEY", "")
    monkeypatch.setenv("UK_SPONSOR_REGISTER_CSV_URL", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'unused.db'}")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.database import get_session
    from app.main import app

    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(test_engine)

    def get_test_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        c.headers.update({"X-API-Key": "test-key-123"})
        yield c

    app.dependency_overrides.clear()
    get_settings.cache_clear()
