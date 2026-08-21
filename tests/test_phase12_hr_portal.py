import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_hr_portal_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "HR Recruitment Command Center" in response.text
    assert "GWC DATA.AI" in response.text
    assert "Run Resume Screening Drive" in response.text


def test_hr_portal_dashboard_endpoint():
    response = client.get("/hr-portal")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Candidate Resume Screening Digest" in response.text or "HR Recruitment Command Center" in response.text


def test_trigger_batch_api_endpoint():
    response = client.post(
        "/api/v1/applications/trigger-batch",
        json={
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1ADbUgOVNNCAxFhZGpTxnOpHtmIeSF6MkMMyeI55ABQk/edit",
            "gid": "1147998574",
            "hr_email": "akashchandrasekar24@gmail.com"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "metrics" in data
    assert data["metrics"]["total"] >= 0


def test_selected_candidates_only_filtering():
    response = client.get("/api/v1/applications?status_filter=SHORTLISTED")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    for candidate in data["candidates"]:
        status = candidate.get("status") or candidate.get("system_decision")
        assert status == "SHORTLISTED"

