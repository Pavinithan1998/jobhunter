import pytest

from app.services import uk_sponsor_register


@pytest.fixture(autouse=True)
def isolated_register_cache(tmp_path, monkeypatch):
    """Point the register's cache files at a temp dir and reset its in-memory state per test."""
    monkeypatch.setattr(uk_sponsor_register, "CACHE_CSV_PATH", tmp_path / "register.csv")
    monkeypatch.setattr(uk_sponsor_register, "META_PATH", tmp_path / "register_meta.json")
    monkeypatch.setattr(uk_sponsor_register, "_cache_mtime", None)
    monkeypatch.setattr(uk_sponsor_register, "_normalized_names", set())
    monkeypatch.setattr(uk_sponsor_register, "_by_first_word", {})
    yield


def _write_fake_register(path, rows):
    import csv

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Organisation Name", "Town/City", "Route"])
        for row in rows:
            writer.writerow([row, "London", "Skilled Worker"])


def test_is_licensed_none_when_register_not_downloaded():
    status, reasoning = uk_sponsor_register.is_licensed("Acme Ltd")
    assert status is None
    assert "hasn't been downloaded" in reasoning


def test_is_licensed_exact_match_after_manual_cache_write():
    _write_fake_register(uk_sponsor_register.CACHE_CSV_PATH, ["Acme Limited", "Globex Corp"])
    status, reasoning = uk_sponsor_register.is_licensed("Acme Ltd")  # differs only by suffix
    assert status is True
    assert "match" in reasoning.lower()


def test_is_licensed_false_when_not_present():
    _write_fake_register(uk_sponsor_register.CACHE_CSV_PATH, ["Acme Limited"])
    status, reasoning = uk_sponsor_register.is_licensed("Totally Different Co")
    assert status is False
    assert "No match" in reasoning


def test_is_licensed_empty_name_returns_none():
    _write_fake_register(uk_sponsor_register.CACHE_CSV_PATH, ["Acme Limited"])
    status, reasoning = uk_sponsor_register.is_licensed("   ")
    assert status is None


def test_get_status_reflects_no_download(isolated_register_cache):
    status = uk_sponsor_register.get_status()
    assert status["downloaded"] is False
    assert status["record_count"] == 0


def test_manual_job_gets_uk_register_checked_by_default(client):
    """GB is the default target country, so new jobs get a register lookup out of the box."""
    _write_fake_register(uk_sponsor_register.CACHE_CSV_PATH, ["Acme Limited"])
    job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme Ltd", "description": "Build things.", "country": "GB"},
    ).json()
    assert job["uk_sponsor_licensed"] is True


def test_uk_register_check_skipped_when_gb_not_a_target_country(client):
    client.post("/api/settings", json={"target_countries": "us"})
    job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme Ltd", "description": "Build things.", "country": "US"},
    ).json()
    assert job["uk_sponsor_licensed"] is None
    assert "isn't one of your target countries" in job["uk_sponsor_reasoning"]


def test_uk_sponsor_register_refresh_endpoint_uses_override_url(client, monkeypatch):
    """POST /api/sources/uk-sponsor-register/refresh should work end to end against a fake CSV server."""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.text = content.decode()

        def raise_for_status(self):
            pass

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *args, **kwargs):
            csv_bytes = b"Organisation Name,Town/City,Route\nFake Sponsor Ltd,London,Skilled Worker\n"
            return FakeResponse(csv_bytes)

    monkeypatch.setenv("UK_SPONSOR_REGISTER_CSV_URL", "https://example.com/fake-register.csv")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(uk_sponsor_register.httpx, "AsyncClient", FakeAsyncClient)

    resp = client.post("/api/sources/uk-sponsor-register/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["downloaded"] is True
    assert body["record_count"] == 1

    status_resp = client.get("/api/sources/uk-sponsor-register/status")
    assert status_resp.json()["downloaded"] is True
