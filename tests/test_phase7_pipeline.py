import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.application import ApplicationIngestRequest
from app.services.resume_processor import ResumeProcessorService
from app.services.csv_storage import CSVStorageService
from tests.test_phase1_ingestion import generate_hmac_signature
from app.core.config import settings

client = TestClient(app)


@pytest.fixture
def temp_processor_csv(tmp_path):
    csv_file = str(tmp_path / "pipeline_screening_results.csv")
    storage = CSVStorageService(csv_file)
    processor = ResumeProcessorService(storage_service=storage)
    return processor, storage


def test_resume_processor_pipeline_end_to_end(temp_processor_csv):
    processor, storage = temp_processor_csv

    payload = ApplicationIngestRequest(
        candidate_id="CAN-PIPELINE-001",
        timestamp="2026-08-17T15:00:00Z",
        full_name="Akash Chandrasekar",
        email="akash.pipeline@example.com",
        phone="+1-555-0199",
        location="San Francisco, CA",
        job_role="PYTHON_DEV",
        years_of_experience=3.0,
        resume_file_id="mock_drive_file_999",
        form_response_id="RESP-PIPE-001"
    )

    result = processor.process_application(payload)

    assert result["candidate_id"] == "CAN-PIPELINE-001"
    assert result["processing_status"] == "COMPLETED"
    assert "decision_reason" in result
    assert len(result["decision_reason"]) > 0

    # Verify CSV storage contains record
    csv_record = storage.get_candidate("CAN-PIPELINE-001")
    assert csv_record is not None
    assert csv_record["email"] == "akash.pipeline@example.com"
    assert csv_record["job_role"] == "PYTHON_DEV"


def test_hr_override_api():
    # First create candidate directly in CSV ledger
    storage = CSVStorageService()
    storage.save_screening_result({
        "candidate_id": "CAN-OVERRIDE-100",
        "candidate_name": "Dave Analyst",
        "email": "dave@example.com",
        "job_role": "DATA_ANALYST",
        "mandatory_passed": True,
        "weighted_score": 68.0,
        "system_decision": "HR_REVIEW",
        "decision_reason": "HR_REVIEW: Score 68.0/100 falls in review range."
    })

    # Call HR override endpoint
    response = client.post(
        "/api/v1/applications/CAN-OVERRIDE-100/override",
        json={
            "override_decision": "SHORTLISTED",
            "override_reason": "Approved during interview sync."
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["candidate"]["hr_override_decision"] == "SHORTLISTED"
    assert data["candidate"]["hr_override_reason"] == "Approved during interview sync."
