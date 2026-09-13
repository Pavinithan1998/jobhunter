from app.services.sources.base import RawJob
from app.models import SourceType


def test_search_web_without_key_returns_clean_400(client):
    resp = client.post("/api/jobs/search-web", json={"query": "ML Engineer"})
    assert resp.status_code == 400
    assert "SERPAPI_KEY" in resp.json()["detail"]


def test_search_web_stores_and_returns_jobs(client, monkeypatch):
    async def fake_search(self, query, location="", country="", remote_only=False):
        return [
            RawJob(
                source=SourceType.web_search,
                source_job_id="serp-1",
                title="ML Engineer",
                company="Internet Co",
                location="London",
                country="GB",
                remote=True,
                description="Build models. No visa sponsorship.",
                url="https://example.com/job/serp-1",
            )
        ]

    from app.services.sources.web_search import WebJobSearchConnector

    monkeypatch.setattr(WebJobSearchConnector, "search", fake_search)

    resp = client.post(
        "/api/jobs/search-web", json={"query": "ML Engineer", "location": "London", "country": "gb"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fetched"] == 1
    assert body["new"] == 1
    assert body["duplicates"] == 0
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["source"] == "web_search"
    assert body["jobs"][0]["sponsorship_status"] == "unlikely"

    # appears in the normal job list too, like any other source
    resp = client.get("/api/jobs")
    assert any(j["title"] == "ML Engineer" and j["source"] == "web_search" for j in resp.json())


def test_search_web_dedupes_on_second_call(client, monkeypatch):
    async def fake_search(self, query, location="", country="", remote_only=False):
        return [
            RawJob(
                source=SourceType.web_search,
                source_job_id="serp-dupe",
                title="Data Scientist",
                company="Internet Co",
                description="Interesting role.",
            )
        ]

    from app.services.sources.web_search import WebJobSearchConnector

    monkeypatch.setattr(WebJobSearchConnector, "search", fake_search)

    client.post("/api/jobs/search-web", json={"query": "Data Scientist"})
    resp = client.post("/api/jobs/search-web", json={"query": "Data Scientist"})
    assert resp.status_code == 200
    assert resp.json()["new"] == 0
    assert resp.json()["duplicates"] == 1
