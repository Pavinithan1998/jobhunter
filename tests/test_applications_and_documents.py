def _make_job(client, **overrides):
    payload = {"title": "ML Engineer", "company": "Acme", "description": "Build LLM pipelines."}
    payload.update(overrides)
    return client.post("/api/sources/manual-job", json=payload).json()


def test_mark_applied(client):
    job = _make_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/apply", params={"notes": "Submitted via company site"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    assert resp.json()["application_stage"] == "no_response"

    resp = client.get(f"/api/jobs/{job['id']}/events")
    events = resp.json()
    assert any(e["event_type"] == "applied" for e in events)


def test_application_stage_progression(client):
    job = _make_job(client)
    client.post(f"/api/jobs/{job['id']}/apply")

    resp = client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "responded", "notes": "Got an auto-reply"})
    assert resp.status_code == 200
    assert resp.json()["application_stage"] == "responded"
    assert resp.json()["status"] == "applied"  # "responded" doesn't change the coarse status

    resp = client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "interviewing"})
    assert resp.json()["application_stage"] == "interviewing"
    assert resp.json()["status"] == "interviewing"

    resp = client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "offer"})
    assert resp.json()["application_stage"] == "offer"
    assert resp.json()["status"] == "offer"

    events = client.get(f"/api/jobs/{job['id']}/events").json()
    assert sum(1 for e in events if e["event_type"] == "stage_change") == 3


def test_application_stage_rejected_before_applying(client):
    job = _make_job(client)
    resp = client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "responded"})
    assert resp.status_code == 400
    assert "hasn't been marked applied" in resp.json()["detail"]


def test_application_stage_invalid_value_rejected(client):
    job = _make_job(client)
    client.post(f"/api/jobs/{job['id']}/apply")
    resp = client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "ghosted"})
    assert resp.status_code == 422


def test_add_event_updates_status(client):
    job = _make_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/events", json={"event_type": "interview", "notes": "Screen booked"})
    assert resp.status_code == 200
    updated = client.get(f"/api/jobs/{job['id']}").json()
    assert updated["status"] == "interviewing"
    assert updated["application_stage"] == "interviewing"


def test_note_event_does_not_change_status(client):
    job = _make_job(client)
    client.patch(f"/api/jobs/{job['id']}/status", json={"status": "shortlisted"})
    client.post(f"/api/jobs/{job['id']}/events", json={"event_type": "note", "notes": "Following up next week"})
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "shortlisted"


def test_invalid_event_type_rejected(client):
    job = _make_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/events", json={"event_type": "ghosted", "notes": ""})
    assert resp.status_code == 422


def test_list_applications_filters_to_pipeline_statuses(client):
    j1 = _make_job(client, title="Job A")
    _make_job(client, title="Job B")  # stays 'new', should not appear
    client.post(f"/api/jobs/{j1['id']}/apply")

    resp = client.get("/api/applications")
    assert resp.status_code == 200
    titles = [j["title"] for j in resp.json()]
    assert titles == ["Job A"]


def test_list_applications_filters_by_channel(client):
    manual_job = _make_job(client, title="Manual Find")
    client.post(f"/api/jobs/{manual_job['id']}/apply")
    assert manual_job["application_channel"] == "manual_search"

    resp = client.get("/api/applications", params={"channel": "manual_search"})
    assert len(resp.json()) == 1
    assert resp.json()[0]["title"] == "Manual Find"

    resp = client.get("/api/applications", params={"channel": "automated_search"})
    assert resp.json() == []


def test_list_applications_filters_by_stage(client):
    job = _make_job(client)
    client.post(f"/api/jobs/{job['id']}/apply")
    client.patch(f"/api/jobs/{job['id']}/application-stage", json={"stage": "interviewing"})

    resp = client.get("/api/applications", params={"stage": "interviewing"})
    assert len(resp.json()) == 1

    resp = client.get("/api/applications", params={"stage": "no_response"})
    assert resp.json() == []


def test_tailor_requires_cv(client):
    job = _make_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/tailor", json={"generate_cover_letter": True})
    assert resp.status_code == 400
    assert "CV" in resp.json()["detail"]


def test_tailor_requires_llm_key_after_cv_uploaded(client, tmp_path):
    from docx import Document

    client.post("/api/profile", json={"full_name": "Test User"})
    doc = Document()
    doc.add_paragraph("Test User - ML Engineer")
    cv_path = tmp_path / "cv.docx"
    doc.save(str(cv_path))
    with open(cv_path, "rb") as f:
        client.post("/api/profile/cv", files={"file": ("cv.docx", f, "application/octet-stream")})

    job = _make_job(client)
    resp = client.post(f"/api/jobs/{job['id']}/tailor", json={"generate_cover_letter": True})
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]
