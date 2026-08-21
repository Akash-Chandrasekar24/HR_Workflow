import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from app.main import app
from app.services.domo_service import DomoService, domo_service
from app.services.csv_storage import CSVStorageService

client = TestClient(app)
storage = CSVStorageService()


@pytest.fixture(autouse=True)
def clean_db():
    storage.clear_ledger()
    yield
    storage.clear_ledger()


def test_domo_csv_formatter_schema():
    """Verify that Domo CSV formatting includes date in Col 1 and resume_file in Col 23."""
    records = [
        {
            "candidate_id": "CAN-DOMO-001",
            "candidate_name": "Deepak Raj",
            "email": "deepak@example.com",
            "job_role": "AI_ENGINEER",
            "status": "SHORTLISTED",
            "weightage_score": 88.5,
            "reasoning": "Strong PyTorch and GenAI background.",
            "resume_file": "1AbCdEfGhIjKlMnOpQrStUv"
        }
    ]

    service = DomoService()
    csv_text = service.format_records_as_csv(records)

    lines = csv_text.strip().split("\r\n" if "\r\n" in csv_text else "\n")
    header_cols = lines[0].split(",")
    data_cols = lines[1].split(",")

    assert header_cols[0] == "date"
    assert header_cols[-1] == "resume_file"
    assert "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUv/view" in csv_text


def test_domo_push_records_audit_and_fallback():
    """Verify that push_records_to_domo saves audit files and returns structured status."""
    service = DomoService()
    records = [
        {
            "candidate_id": "CAN-DOMO-002",
            "candidate_name": "Sneha Gupta",
            "email": "sneha@example.com",
            "job_role": "FULLSTACK_DEV",
            "status": "SHORTLISTED",
            "weightage_score": 91.0,
            "reasoning": "React and FastAPI expert.",
            "resume_file": "https://drive.google.com/file/d/2XyZ/view"
        }
    ]

    res = service.push_records_to_domo(records)
    assert res["status"] == "SUCCESS"
    assert res["count"] >= 1
    assert "audit_file" in res or "destination" in res

    # Verify audit file exists on disk
    if "audit_file" in res:
        audit_path = Path(res["audit_file"])
        assert audit_path.exists()
        assert "CAN-DOMO-002" in audit_path.read_text(encoding="utf-8")


def test_finalize_batch_executes_domo_push():
    """Verify that calling finalize-batch endpoint automatically executes Domo sync in backend."""
    storage.save_screening_result({
        "candidate_id": "CAN-DOMO-FINALIZE",
        "candidate_name": "Arun Kumar",
        "email": "arun@example.com",
        "job_role": "DATA_ANALYST",
        "status": "SHORTLISTED",
        "weightage_score": 85.0,
        "reasoning": "SQL and Tableau visualization expert.",
        "assigned_employee_email": "interviewer@company.com",
        "assigned_employee_name": "Lead Analyst"
    })

    resp = client.post("/api/v1/applications/finalize-batch", json={
        "hr_email": "hr-test@company.com",
        "dispatch_interviewer_emails": False,
        "move_drive_files": False
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert "domo_sync" in data
    assert data["domo_sync"]["status"] == "SUCCESS"
    assert data["domo_sync"]["count"] >= 1
