import os
import io
import json
import pytest
import openpyxl
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.services.referral_service import ReferralService, referral_service
from app.services.csv_storage import CSVStorageService
from app.services.email_service import EmailService


@pytest.fixture(autouse=True)
def clean_test_referrals_and_csv(tmp_path):
    """Isolate referral registry and CSV storage for every test."""
    test_json = tmp_path / "test_referrals.json"
    test_csv = tmp_path / "test_screening.csv"

    ref_service = ReferralService(referral_json_path=str(test_json))
    ref_service.clear_referrals()  # Start completely empty
    csv_service = CSVStorageService(csv_path=str(test_csv))

    # Temporarily patch singleton references
    from app.services import referral_service as rs_module
    from app.api.routes import referrals as ref_routes

    orig_service = rs_module.referral_service
    rs_module.referral_service = ref_service
    ref_routes.referral_service = ref_service
    ref_routes.storage_service = csv_service

    yield ref_service, csv_service

    # Restore
    rs_module.referral_service = orig_service
    ref_routes.referral_service = orig_service


def test_referral_service_lifecycle(clean_test_referrals_and_csv):
    ref_svc, _ = clean_test_referrals_and_csv

    # 1. Initial state
    assert len(ref_svc.get_all_referrals()) == 0

    # 2. Add single referral
    item = ref_svc.add_or_update_referral(
        candidate_name="Alice Referral",
        candidate_email="alice.ref@example.com",
        candidate_phone="+1234567890",
        referred_by_name="Sanjay Kumar",
        referred_by_id="EMP-204",
        referred_by_email="sanjay.k@gwcdata.ai",
        department="AI Solutions",
        notes="Former colleague with 4 yrs PyTorch experience"
    )
    assert item["candidate_email"] == "alice.ref@example.com"
    assert len(ref_svc.get_all_referrals()) == 1

    # 3. Match finding
    matched = ref_svc.find_referral_match({"email": "ALICE.REF@EXAMPLE.COM"})
    assert matched is not None
    assert matched["referred_by_name"] == "Sanjay Kumar"
    assert matched["referred_by_id"] == "EMP-204"

    # 4. Clear referrals
    ref_svc.clear_referrals()
    assert len(ref_svc.get_all_referrals()) == 0


def test_referral_excel_template_generation_and_import(clean_test_referrals_and_csv):
    ref_svc, _ = clean_test_referrals_and_csv

    # Generate template
    excel_bytes = ref_svc.generate_sample_referral_template_excel()
    assert len(excel_bytes) > 0

    # Read back generated template with openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    ws = wb.active
    assert ws.title == "Employee Referrals"
    assert ws.cell(row=1, column=1).value == "Candidate Name"

    # Import generated sample template
    imported = ref_svc.import_referrals_from_excel_bytes(excel_bytes, filename="Sample_Referrals.xlsx")
    assert len(imported) >= 2
    emails = [r["candidate_email"].lower() for r in imported]
    assert "sneha.venkat@gmail.com" in emails
    assert "karthik.r@example.com" in emails
    assert "rahul.sharma@example.com" in emails


def test_referral_cross_referencing_and_rejection_interception(clean_test_referrals_and_csv):
    ref_svc, csv_svc = clean_test_referrals_and_csv

    # Register referral
    ref_svc.add_or_update_referral(
        candidate_name="Bob Lowscore",
        candidate_email="bob.low@example.com",
        referred_by_name="Deepak Rao",
        referred_by_id="EMP-102",
        referred_by_email="deepak.r@gwcdata.ai",
        department="GenAI"
    )

    # Save a low-scoring candidate (rejected by AI)
    cand_record = {
        "candidate_id": "CAND-999",
        "candidate_name": "Bob Lowscore",
        "email": "bob.low@example.com",
        "job_role": "AI_ENGINEER",
        "status": "REJECTED",
        "weightage_score": 45.0,
        "reasoning": "Missing PyTorch production background.",
        "hr_approval_status": "PENDING_HR_APPROVAL"
    }
    csv_svc.save_screening_result(cand_record)

    # Read records back
    records = csv_svc.get_all_records()
    assert len(records) == 1
    rec = records[0]

    assert rec["is_referred"] is True
    assert rec["referred_by_name"] == "Deepak Rao"
    assert rec["referral_alert"] == "REFERRED_REJECTED"
    assert "Referred by Deepak Rao" in rec["referral_alert_message"]


def test_referral_api_endpoints(clean_test_referrals_and_csv):
    ref_svc, _ = clean_test_referrals_and_csv
    client = TestClient(app)

    # 1. Download template
    res = client.get("/api/v1/referrals/template/excel")
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    excel_bytes = res.content

    # 2. Upload template back
    files = {"file": ("Referrals_Test.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_res = client.post("/api/v1/referrals/upload-roster", files=files)
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["status"] == "SUCCESS"
    assert data["count"] >= 2

    # 3. GET /api/v1/referrals
    list_res = client.get("/api/v1/referrals")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["count"] >= 2

    # 4. DELETE /api/v1/referrals
    del_res = client.delete("/api/v1/referrals")
    assert del_res.status_code == 200
    assert client.get("/api/v1/referrals").json()["count"] == 0


def test_email_digest_contains_referral_section():
    email_svc = EmailService()
    shortlisted = [
        {
            "candidate_name": "Alice High",
            "email": "alice@example.com",
            "job_role": "AI_ENGINEER",
            "reasoning": "Top match",
            "weighted_score": 95.0,
            "status": "SHORTLISTED"
        }
    ]
    rejected = [
        {
            "candidate_name": "Bob Referred",
            "email": "bob@example.com",
            "job_role": "PYTHON_DEV",
            "reasoning": "Needs more testing exp",
            "weighted_score": 52.0,
            "status": "REJECTED",
            "is_referred": True,
            "referred_by_name": "Sanjay Kumar",
            "referred_by_id": "EMP-204"
        }
    ]

    html = email_svc._build_html_email_template(
        total_count=2,
        shortlisted_count=1,
        review_count=0,
        rejected_count=1,
        shortlisted_candidates=shortlisted,
        timestamp_str="2026-08-19 18:00:00",
        rejected_candidates=rejected
    )

    assert "Employee Referrals Summary" in html
    assert "Bob Referred" in html
    assert "Sanjay Kumar" in html
    assert "AI Rejected — HR Review Recommended" in html
