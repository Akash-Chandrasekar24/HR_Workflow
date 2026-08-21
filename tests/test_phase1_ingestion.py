import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services.google_drive import GoogleDriveService

client = TestClient(app)


def generate_hmac_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    ).hexdigest()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"


def test_readiness_check():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "READY"


def test_application_ingestion_success():
    payload = {
        "candidate_id": "CAN-2026-TEST01",
        "timestamp": "2026-08-17T14:30:00Z",
        "full_name": "Test Candidate",
        "email": "test.candidate@example.com",
        "phone": "+15550199",
        "location": "New York, NY",
        "job_role": "PYTHON_DEV",
        "years_of_experience": 3.0,
        "resume_file_id": "1MockGoogleDriveFileId123456789",
        "form_response_id": "RESP-TEST-001"
    }
    
    import json
    raw_body = json.dumps(payload).encode("utf-8")
    signature = generate_hmac_signature(raw_body, settings.HMAC_SECRET)

    response = client.post(
        "/api/v1/applications",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": signature
        }
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ACCEPTED"
    assert data["candidate_id"] == "CAN-2026-TEST01"
    assert "enqueued successfully" in data["message"]


def test_google_drive_mock_retrieval():
    drive_service = GoogleDriveService()
    metadata = drive_service.get_file_metadata("mock_file_123")
    assert metadata["id"] == "mock_file_123"
    
    file_bytes, filename, mime_type = drive_service.download_file("mock_file_123")
    assert len(file_bytes) > 0
    assert filename is not None
    assert mime_type == "application/pdf"
