from app.models import SponsorshipStatus
from app.services import sponsorship


def test_classifies_unlikely_from_no_sponsorship_phrase():
    status, reasoning = sponsorship.classify("We are unable to sponsor visas for this role.")
    assert status == SponsorshipStatus.unlikely
    assert reasoning


def test_classifies_unlikely_from_right_to_work_requirement():
    status, _ = sponsorship.classify("Candidates must already have the right to work in the UK.")
    assert status == SponsorshipStatus.unlikely


def test_classifies_likely_from_explicit_sponsorship_offer():
    status, _ = sponsorship.classify("Visa sponsorship is available for the right candidate.")
    assert status == SponsorshipStatus.likely


def test_classifies_unclear_when_not_mentioned():
    status, _ = sponsorship.classify("We are looking for a skilled Python developer.")
    assert status == SponsorshipStatus.unclear


def test_manual_job_gets_sponsorship_classification(client):
    resp = client.post(
        "/api/sources/manual-job",
        json={
            "title": "ML Engineer",
            "company": "Acme",
            "description": "No visa sponsorship is offered for this position.",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["sponsorship_status"] == "unlikely"
    assert resp.json()["sponsorship_reasoning"]
