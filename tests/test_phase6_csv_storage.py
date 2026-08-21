import pytest
import os
from pathlib import Path
from app.services.csv_storage import CSVStorageService


@pytest.fixture
def temp_csv_path(tmp_path):
    return str(tmp_path / "test_screening_results.csv")


def test_csv_storage_save_and_retrieve(temp_csv_path):
    storage = CSVStorageService(temp_csv_path)

    record = {
        "candidate_id": "CAN-TEST-001",
        "candidate_name": "Akash Chandrasekar",
        "email": "akash@example.com",
        "phone": "+1-555-0199",
        "job_role": "PYTHON_DEV",
        "resume_file_id": "drive_file_123",
        "resume_hash": "a1b2c3d4e5f6",
        "mandatory_passed": True,
        "weighted_score": 88.5,
        "system_decision": "SHORTLISTED",
        "decision_reason": "SHORTLISTED: Passed all mandatory checks. Total score 88.5/100.",
        "score_breakdown": {"Python": 30.0, "FastAPI": 25.0},
        "evidence_snippets": {"Python": ["3 years of experience"]},
        "processing_status": "COMPLETED"
    }

    saved = storage.save_screening_result(record)
    assert saved["candidate_id"] == "CAN-TEST-001"
    assert saved["system_decision"] == "SHORTLISTED"

    retrieved = storage.get_candidate("CAN-TEST-001")
    assert retrieved is not None
    assert retrieved["candidate_name"] == "Akash Chandrasekar"
    assert retrieved["mandatory_passed"] is True
    assert retrieved["weighted_score"] == 88.5
    assert "SHORTLISTED: Passed all mandatory checks" in retrieved["decision_reason"]


def test_csv_storage_hr_override(temp_csv_path):
    storage = CSVStorageService(temp_csv_path)

    record = {
        "candidate_id": "CAN-TEST-002",
        "candidate_name": "Jane Smith",
        "email": "jane@example.com",
        "job_role": "AI_ENGINEER",
        "mandatory_passed": True,
        "weighted_score": 72.0,
        "system_decision": "HR_REVIEW",
        "decision_reason": "HR_REVIEW: Score 72.0/100 falls in review range."
    }

    storage.save_screening_result(record)

    # HR performs override
    updated = storage.save_hr_override(
        candidate_id="CAN-TEST-002",
        override_decision="SHORTLISTED",
        override_reason="Strong past project experience verified in recruiter call."
    )

    assert updated is not None
    assert updated["hr_override_decision"] == "SHORTLISTED"
    assert updated["hr_override_reason"] == "Strong past project experience verified in recruiter call."

    # Verify retrieval reflects override
    fetched = storage.get_candidate("CAN-TEST-002")
    assert fetched["hr_override_decision"] == "SHORTLISTED"
