def _make_job(client, **overrides):
    payload = {
        "title": "ML Engineer",
        "company": "Acme",
        "description": "Build LLM pipelines with LangChain.",
        "location": "London",
        "remote": True,
    }
    payload.update(overrides)
    resp = client.post("/api/sources/manual-job", json=payload)
    assert resp.status_code == 200
    return resp.json()


def test_list_jobs_empty_initially(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_jobs_filters(client):
    _make_job(client, title="ML Engineer", remote=True)
    _make_job(client, title="Data Analyst", remote=False)

    resp = client.get("/api/jobs")
    assert len(resp.json()) == 2

    resp = client.get("/api/jobs", params={"work_mode": "remote"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "ML Engineer"

    resp = client.get("/api/jobs", params={"search": "analyst"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Data Analyst"


def test_get_single_job(client):
    job = _make_job(client)
    resp = client.get(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job["id"]


def test_get_missing_job_404s(client):
    resp = client.get("/api/jobs/999")
    assert resp.status_code == 404


def test_update_job_status(client):
    job = _make_job(client)
    resp = client.patch(f"/api/jobs/{job['id']}/status", json={"status": "shortlisted", "notes": "Looks good"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "shortlisted"

    resp = client.get(f"/api/jobs/{job['id']}/events")
    assert resp.status_code == 200
    assert any(e["notes"] == "Looks good" for e in resp.json())


def test_update_status_rejects_invalid_value(client):
    job = _make_job(client)
    resp = client.patch(f"/api/jobs/{job['id']}/status", json={"status": "not-a-real-status"})
    assert resp.status_code == 422


def test_delete_job(client):
    job = _make_job(client)
    resp = client.delete(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404


def test_manual_job_dedupe_not_enforced_across_calls(client):
    # Each manual-job call is treated as a distinct listing (unlike fetched
    # jobs, which dedupe on source_job_id) -- this documents that behaviour.
    _make_job(client, title="ML Engineer")
    _make_job(client, title="ML Engineer")
    resp = client.get("/api/jobs")
    assert len(resp.json()) == 2


def test_score_batch_without_llm_key_reports_error_not_crash(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    _make_job(client)
    resp = client.post("/api/jobs/score-batch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scored"] == 0
    assert any("ANTHROPIC_API_KEY" in e for e in body["errors"])


def test_daily_digest_empty_without_scored_jobs(client):
    _make_job(client)  # unscored -- won't clear the min_score threshold
    resp = client.get("/api/jobs/digest/today")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
