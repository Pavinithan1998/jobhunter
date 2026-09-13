def test_dashboard_summary_shape_and_counts(client):
    j1 = client.post(
        "/api/sources/manual-job", json={"title": "A", "company": "X", "description": "d"}
    ).json()
    client.post("/api/sources/manual-job", json={"title": "B", "company": "Y", "description": "d"})
    client.post(f"/api/jobs/{j1['id']}/apply")

    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_jobs"] == 2
    assert body["by_status"]["applied"] == 1
    assert body["by_status"]["new"] == 1
    assert body["new_today"] == 2
    assert body["applied_last_7_days"] == 1
