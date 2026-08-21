import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.csv_storage import CSVStorageService
from app.services.hitl_service import GeminiHITLService

client = TestClient(app)
storage = CSVStorageService()


@pytest.fixture(autouse=True)
def clean_db():
    storage.clear_ledger()
    yield
    storage.clear_ledger()


def test_initial_screening_sets_pending_hr_approval():
    """Verify that a candidate with score below 90% defaults to PENDING_HR_APPROVAL."""
    record = {
        "candidate_id": "CAN-HITL-001",
        "candidate_name": "Dev Sharma",
        "email": "dev.sharma@example.com",
        "phone": "+919876543210",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weightage_score": 88.5,
        "reasoning": "Qualified based on LLM and PyTorch skills."
    }
    storage.save_screening_result(record)

    saved = storage.get_record_by_id("CAN-HITL-001")
    assert saved is not None
    assert saved["hr_approval_status"] == "PENDING_HR_APPROVAL"
    assert saved["status"] == "SHORTLISTED"


def test_ai_auto_accepts_candidate_with_90_plus_score():
    """Verify that a top candidate scoring 90%+ is automatically accepted by AI."""
    record = {
        "candidate_id": "CAN-AUTO-901",
        "candidate_name": "Siddharth Rao",
        "email": "siddharth.rao@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weightage_score": 94.5,
        "reasoning": "Exceptional PyTorch, LangChain, and RAG expertise."
    }
    storage.save_screening_result(record)

    saved = storage.get_record_by_id("CAN-AUTO-901")
    assert saved is not None
    assert saved["hr_approval_status"] == "HR_APPROVED"
    assert saved["status"] == "SHORTLISTED"
    assert saved["interview_status"] == "UNASSIGNED"


def test_hr_approve_endpoint():
    """Verify that HR can approve a pending candidate in the review pool."""
    record = {
        "candidate_id": "CAN-HITL-002",
        "candidate_name": "Priya Patel",
        "email": "priya.patel@example.com",
        "phone": "+919876543211",
        "job_role": "FULLSTACK_DEV",
        "status": "SHORTLISTED",
        "weightage_score": 82.0,
        "reasoning": "Strong React and FastAPI background."
    }
    storage.save_screening_result(record)

    resp = client.post("/api/v1/applications/CAN-HITL-002/hr-approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["candidate"]["hr_approval_status"] == "HR_APPROVED"
    assert data["candidate"]["status"] == "SHORTLISTED"

    # Confirm in storage
    saved = storage.get_record_by_id("CAN-HITL-002")
    assert saved["hr_approval_status"] == "HR_APPROVED"


def test_hr_re_evaluate_endpoint_with_feedback():
    """Verify that HR feedback triggers re-evaluation and updates score & rationale."""
    record = {
        "candidate_id": "CAN-HITL-003",
        "candidate_name": "Rohan Gupta",
        "email": "rohan.gupta@example.com",
        "phone": "+919876543212",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weightage_score": 75.0,
        "reasoning": "Moderate AI experience with basic Python."
    }
    storage.save_screening_result(record)

    feedback_payload = {
        "hr_feedback": "The candidate has demonstrated strong PyTorch hands-on project portfolio in the live technical screen. Please upgrade score."
    }

    resp = client.post("/api/v1/applications/CAN-HITL-003/hr-re-evaluate", json=feedback_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["re_evaluation"]["revised_score"] >= 75.0
    assert len(data["candidate"]["hr_feedback"]) > 0


def test_hr_reject_endpoint():
    """Verify that HR can explicitly reject a candidate with recruiter notes."""
    record = {
        "candidate_id": "CAN-HITL-004",
        "candidate_name": "Kiran Kumar",
        "email": "kiran@example.com",
        "job_role": "DATA_ANALYST",
        "status": "SHORTLISTED",
        "weightage_score": 80.0,
        "reasoning": "Standard analyst skills."
    }
    storage.save_screening_result(record)

    resp = client.post("/api/v1/applications/CAN-HITL-004/hr-reject", json={"reason": "Lack of required Snowflake experience."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["candidate"]["hr_approval_status"] == "REJECTED_BY_HR"
    assert data["candidate"]["status"] == "REJECTED"
    assert data["candidate"]["hr_recruiter_notes"] == "Lack of required Snowflake experience."


def test_hitl_service_direct_re_evaluation():
    """Verify GeminiHITLService fallback and re-evaluation calculations."""
    service = GeminiHITLService(gemini_api_key="fake-key-for-test-fallback")
    cand = {
        "candidate_name": "Anil Verma",
        "job_role": "AI_ENGINEER",
        "weightage_score": 70.0,
        "reasoning": "Standard score."
    }
    result = service.re_evaluate_candidate(cand, hr_feedback="Candidate demonstrated excellent deep learning models, please increase score.")
    assert result is not None
    assert result["revised_score"] >= 70.0
    assert result["suggested_action"] == "APPROVE"


def test_bulk_hr_approve_endpoint():
    """Verify that multiple candidates can be approved in bulk in the review pool."""
    for i in range(1, 6):
        storage.save_screening_result({
            "candidate_id": f"CAN-BULK-{i:03d}",
            "candidate_name": f"Bulk Candidate {i}",
            "email": f"bulk{i}@example.com",
            "job_role": "AI_ENGINEER",
            "status": "SHORTLISTED",
            "weightage_score": 80.0 + i,
            "reasoning": "Qualified profile."
        })

    # Test 1: Bulk approve by specific candidate IDs
    resp1 = client.post("/api/v1/applications/bulk-hr-approve", json={
        "candidate_ids": ["CAN-BULK-001", "CAN-BULK-002"],
        "approve_all_pending": False
    })
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "SUCCESS"
    assert data1["approved_count"] == 2

    # Test 2: Bulk approve all remaining pending candidates
    resp2 = client.post("/api/v1/applications/bulk-hr-approve", json={
        "approve_all_pending": True
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "SUCCESS"
    assert data2["approved_count"] >= 3


def test_finalize_recruitment_batch_endpoint():
    """Verify that the finalize-batch endpoint cooks the CSV and dispatches digest."""
    storage.save_screening_result({
        "candidate_id": "CAN-FINAL-001",
        "candidate_name": "Akash Final",
        "email": "akash.final@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weightage_score": 92.0,
        "reasoning": "Top score in PyTorch and GenAI.",
        "assigned_employee_email": "interviewer@company.com",
        "assigned_employee_name": "Senior Interviewer"
    })

    # Check batch status before finalize
    st_resp = client.get("/api/v1/applications/batch-status")
    assert st_resp.status_code == 200

    # Finalize batch
    fin_resp = client.post("/api/v1/applications/finalize-batch", json={
        "hr_email": "hr-test@company.com",
        "dispatch_interviewer_emails": False,
        "move_drive_files": False
    })
    assert fin_resp.status_code == 200
    fin_data = fin_resp.json()
    assert fin_data["status"] == "SUCCESS"
    assert "Recruitment Batch Finalized" in fin_data["message"]
    assert storage.is_batch_finalized() is True


def test_bulk_hr_reject_endpoint():
    """Verify that multiple candidates can be bulk rejected."""
    for i in range(1, 4):
        storage.save_screening_result({
            "candidate_id": f"CAN-REJ-{i:03d}",
            "candidate_name": f"Reject Candidate {i}",
            "email": f"rej{i}@example.com",
            "job_role": "DATA_ANALYST",
            "status": "SHORTLISTED",
            "weightage_score": 60.0
        })

    resp = client.post("/api/v1/applications/bulk-hr-reject", json={
        "candidate_ids": ["CAN-REJ-001", "CAN-REJ-002"],
        "reason": "Batch rejected by recruiter"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["rejected_count"] == 2

    rec1 = storage.get_record_by_id("CAN-REJ-001")
    assert rec1["hr_approval_status"] == "REJECTED_BY_HR"
    assert rec1["status"] == "REJECTED"
