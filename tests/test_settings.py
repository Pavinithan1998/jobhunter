def test_settings_404_before_creation(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 404


def test_settings_default_country_is_gb_when_created_with_no_override(client):
    resp = client.post("/api/settings", json={})
    assert resp.status_code == 200
    assert resp.json()["target_countries"] == "GB"
    assert resp.json()["work_mode"] == "any"


def test_settings_create_and_update(client):
    resp = client.post(
        "/api/settings",
        json={
            "target_countries": "gb,us",
            "work_mode": "remote",
            "require_sponsorship": True,
            "excluded_companies": "Bad Corp",
            "digest_min_score": 70,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_countries"] == "gb,us"
    assert body["work_mode"] == "remote"
    assert body["digest_min_score"] == 70

    resp = client.post("/api/settings", json={"target_countries": "ca", "digest_min_score": 50})
    assert resp.status_code == 200
    assert resp.json()["target_countries"] == "ca"
    assert resp.json()["id"] == body["id"]  # same row, upserted


def test_settings_reject_out_of_range_digest_score(client):
    resp = client.post("/api/settings", json={"digest_min_score": 150})
    assert resp.status_code == 422


def test_settings_reject_invalid_work_mode(client):
    resp = client.post("/api/settings", json={"work_mode": "part_time"})
    assert resp.status_code == 422


def test_work_mode_remote_setting_auto_dismisses_non_remote_jobs_on_scoring(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"work_mode": "remote"})
    job = client.post(
        "/api/sources/manual-job",
        json={
            "title": "ML Engineer",
            "company": "Acme",
            "description": "Based in our London office, 5 days a week in the building.",
            "remote": False,
        },
    ).json()
    assert job["work_mode"] == "onsite"

    resp = client.post("/api/jobs/score-batch")
    assert resp.status_code == 200
    assert resp.json()["scored"] == 1

    updated = client.get(f"/api/jobs/{job['id']}").json()
    assert updated["status"] == "dismissed"
    assert "remote-only" in updated["relevance_reasoning"]


def test_work_mode_unclear_is_never_auto_dismissed(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"work_mode": "remote"})
    job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme", "description": "Build pipelines.", "remote": False},
    ).json()
    assert job["work_mode"] == "unclear"

    client.post("/api/jobs/score-batch")
    updated = client.get(f"/api/jobs/{job['id']}").json()
    # unclear work mode is never dismissed by the work_mode filter -- some other
    # outcome is fine (dismissed for another reason, or scored), just not this one.
    assert "settings require remote-only" not in updated["relevance_reasoning"]


def test_hybrid_only_setting_dismisses_remote_and_onsite_jobs(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"work_mode": "hybrid"})
    remote_job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme", "description": "Fully remote role.", "remote": True},
    ).json()
    hybrid_job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme", "description": "Hybrid: 3 days in the office."},
    ).json()
    assert remote_job["work_mode"] == "remote"
    assert hybrid_job["work_mode"] == "hybrid"

    client.post("/api/jobs/score-batch")
    assert client.get(f"/api/jobs/{remote_job['id']}").json()["status"] == "dismissed"
    assert client.get(f"/api/jobs/{hybrid_job['id']}").json()["status"] != "dismissed"


def test_excluded_company_auto_dismissed_on_scoring(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"excluded_companies": "Bad Corp"})
    job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Bad Corp", "description": "Build pipelines."},
    ).json()

    client.post("/api/jobs/score-batch")
    updated = client.get(f"/api/jobs/{job['id']}").json()
    assert updated["status"] == "dismissed"
    assert "excluded companies" in updated["relevance_reasoning"]


def test_require_sponsorship_auto_dismisses_unlikely_jobs_on_scoring(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"require_sponsorship": True})
    job = client.post(
        "/api/sources/manual-job",
        json={
            "title": "ML Engineer",
            "company": "Acme",
            "description": "We are unable to sponsor visas for this role.",
        },
    ).json()
    assert job["sponsorship_status"] == "unlikely"

    client.post("/api/jobs/score-batch")
    updated = client.get(f"/api/jobs/{job['id']}").json()
    assert updated["status"] == "dismissed"
    assert "sponsorship" in updated["relevance_reasoning"].lower()


def test_target_country_mismatch_auto_dismissed_on_scoring(client):
    client.post("/api/profile", json={"full_name": "Test User"})
    client.post("/api/settings", json={"target_countries": "gb"})
    job = client.post(
        "/api/sources/manual-job",
        json={"title": "ML Engineer", "company": "Acme", "description": "Build pipelines.", "country": "US"},
    ).json()

    client.post("/api/jobs/score-batch")
    updated = client.get(f"/api/jobs/{job['id']}").json()
    assert updated["status"] == "dismissed"
    assert "target countries" in updated["relevance_reasoning"]


def test_jobs_filter_by_country_and_sponsorship(client):
    client.post(
        "/api/sources/manual-job",
        json={"title": "A", "company": "X", "description": "d", "country": "GB"},
    )
    client.post(
        "/api/sources/manual-job",
        json={"title": "B", "company": "Y", "description": "No sponsorship available.", "country": "US"},
    )

    resp = client.get("/api/jobs", params={"country": "GB"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "A"

    resp = client.get("/api/jobs", params={"sponsorship": "unlikely"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "B"
