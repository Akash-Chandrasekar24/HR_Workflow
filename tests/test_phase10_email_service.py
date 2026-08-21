import pytest
import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services.email_service import EmailService
from app.services.csv_storage import CSVStorageService

client = TestClient(app)


def test_email_service_html_generation_and_attachment(tmp_path):
    email_service = EmailService()
    temp_csv = str(tmp_path / "test_screening_ledger.csv")
    
    # Create sample ledger
    storage = CSVStorageService(temp_csv)
    storage.save_screening_result({
        "candidate_id": "CAN-EMAIL-001",
        "candidate_name": "Akash C",
        "email": "akash@example.com",
        "phone": "+91 97915 64264",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weighted_score": 88.5,
        "reasoning": "The candidate was selected for the AI Engineer position because they satisfied all mandatory qualifications and demonstrated exceptional hands-on expertise in Python & ML Frameworks."
    })

    candidates = storage.get_all_records()
    res = email_service.send_shortlist_digest(
        recipient_email="hr-test@company.com",
        candidates=candidates,
        csv_attachment_path=temp_csv
    )

    assert res["status"] in ["SENT", "AUDITED_LOCAL"]
    assert res["shortlisted_count"] == 1
    assert res["total_count"] >= 1
    assert res["attachment"] == "test_screening_ledger.csv"


def test_email_digest_api_endpoint():
    storage = CSVStorageService()
    storage.save_screening_result({
        "candidate_id": "CAN-EMAIL-DIGEST",
        "candidate_name": "Digest Candidate",
        "email": "digest@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weightage_score": 85.0,
        "reasoning": "Selected for AI role."
    })

    response = client.post(
        "/api/v1/notifications/email-digest",
        json={"recipient_email": "hr-recruiter@company.com"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "details" in data
    assert data["details"]["shortlisted_count"] >= 1
