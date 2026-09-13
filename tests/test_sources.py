def test_sources_status_shape(client):
    resp = client.get("/api/sources/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adzuna"] is False
    assert body["jooble"] is False
    assert "linkedin" in body and "not supported" in body["linkedin"]
    assert "indeed" in body and "not supported" in body["indeed"]


def test_manual_job_creates_listing(client):
    resp = client.post(
        "/api/sources/manual-job",
        json={
            "title": "ML Engineer",
            "company": "Acme",
            "description": "Build LLM pipelines.",
            "url": "https://linkedin.com/jobs/view/1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manual"
    assert body["status"] == "new"


def test_tracked_company_add_list_delete(client):
    resp = client.post("/api/sources/greenhouse", json={"slug": "stripe", "display_name": "Stripe"})
    assert resp.status_code == 200
    company_id = resp.json()["id"]

    resp = client.get("/api/sources/greenhouse")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # duplicate slug rejected
    resp = client.post("/api/sources/greenhouse", json={"slug": "stripe"})
    assert resp.status_code == 400

    resp = client.delete(f"/api/sources/greenhouse/{company_id}")
    assert resp.status_code == 200
    assert client.get("/api/sources/greenhouse").json() == []


def test_delete_nonexistent_company_404s(client):
    resp = client.delete("/api/sources/greenhouse/999")
    assert resp.status_code == 404
