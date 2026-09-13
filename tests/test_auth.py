def test_health_needs_no_key(client):
    client.headers.pop("X-API-Key")
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_endpoint_rejects_missing_key(client):
    client.headers.pop("X-API-Key")
    resp = client.get("/api/jobs")
    assert resp.status_code == 422  # header is required, so FastAPI validation catches it


def test_protected_endpoint_rejects_wrong_key(client):
    client.headers["X-API-Key"] = "wrong-key"
    resp = client.get("/api/jobs")
    assert resp.status_code == 401


def test_protected_endpoint_accepts_correct_key(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
