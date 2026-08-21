import pytest
from pathlib import Path
from app.services.google_drive_organizer import GoogleDriveFolderOrganizerService, google_drive_organizer

SAMPLE_DRIVE_URL = "https://drive.google.com/drive/folders/1ffGKAYBJDhMVE6oqubPklYnK5NAdBxCZ0sF3HKsJB8XOcp8QwEWh6QGDUW2AKq7rWSDUhSKY"
SAMPLE_DRIVE_ID = "1ffGKAYBJDhMVE6oqubPklYnK5NAdBxCZ0sF3HKsJB8XOcp8QwEWh6QGDUW2AKq7rWSDUhSKY"


def test_extract_folder_id():
    """Verifies Google Drive Folder ID extraction from full URLs, query params, and raw IDs."""
    assert google_drive_organizer.extract_folder_id(SAMPLE_DRIVE_URL) == SAMPLE_DRIVE_ID
    assert google_drive_organizer.extract_folder_id(f"https://drive.google.com/open?id={SAMPLE_DRIVE_ID}") == SAMPLE_DRIVE_ID
    assert google_drive_organizer.extract_folder_id(SAMPLE_DRIVE_ID) == SAMPLE_DRIVE_ID
    assert google_drive_organizer.extract_folder_id("") == ""


def test_normalize_role():
    """Verifies candidate job roles are normalized to clean folder keys."""
    assert google_drive_organizer.normalize_role("AI Enginner") == "AI_Engineer"
    assert google_drive_organizer.normalize_role("AI / ML Lead") == "AI_Engineer"
    assert google_drive_organizer.normalize_role("Full Stack Developer") == "Full_Stack"
    assert google_drive_organizer.normalize_role("Python Dev") == "Full_Stack"
    assert google_drive_organizer.normalize_role("Data Analyst") == "Data_Analyst"
    assert google_drive_organizer.normalize_role("Senior BI Analyst") == "Data_Analyst"


def test_map_status_to_folder():
    """Verifies screening statuses map to Selected or Rejected only (no Review_Pending)."""
    assert google_drive_organizer.map_status_to_folder("SHORTLISTED") == "Selected"
    assert google_drive_organizer.map_status_to_folder("SELECTED") == "Selected"
    assert google_drive_organizer.map_status_to_folder("REJECTED") == "Rejected"
    # HR_REVIEW now defaults to Rejected instead of Review_Pending
    assert google_drive_organizer.map_status_to_folder("HR_REVIEW") == "Rejected"
    assert google_drive_organizer.map_status_to_folder("") == "Rejected"


def test_organize_candidate_resume():
    """Verifies resume organization creates subfolder paths and tracking metadata."""
    res_selected = google_drive_organizer.organize_candidate_resume(
        candidate_id="CAN-TEST-101",
        candidate_name="Akash C",
        job_role="AI Enginner",
        status="SHORTLISTED",
        resume_file_id_or_url="mock_drive_file_999",
        parent_folder_url_or_id=SAMPLE_DRIVE_URL
    )
    assert res_selected["status"] == "SUCCESS"
    assert res_selected["status_folder"] == "Selected"
    assert res_selected["role_folder"] == "AI_Engineer"
    assert res_selected["relative_folder_path"] == "Selected/AI_Engineer"
    assert res_selected["parent_folder_id"] == SAMPLE_DRIVE_ID

    res_rejected = google_drive_organizer.organize_candidate_resume(
        candidate_id="CAN-TEST-102",
        candidate_name="John Doe",
        job_role="Full Stack Developer",
        status="REJECTED",
        resume_file_id_or_url="mock_drive_file_999",
        parent_folder_url_or_id=SAMPLE_DRIVE_URL
    )
    assert res_rejected["status"] == "SUCCESS"
    assert res_rejected["status_folder"] == "Rejected"
    assert res_rejected["role_folder"] == "Full_Stack"
    assert res_rejected["relative_folder_path"] == "Rejected/Full_Stack"


def test_relocate_rejected_to_selected():
    """Verifies that overriding a candidate from Rejected to Selected relocates the resume."""
    # Step 1: Candidate is initially rejected
    res_rej = google_drive_organizer.organize_candidate_resume(
        candidate_id="CAN-OVERRIDE-888",
        candidate_name="Pooja Ramesh",
        job_role="Data Analyst",
        status="REJECTED",
        resume_file_id_or_url="mock_drive_file_999",
        parent_folder_url_or_id=SAMPLE_DRIVE_URL
    )
    assert res_rej["status_folder"] == "Rejected"
    assert res_rej["relative_folder_path"] == "Rejected/Data_Analyst"

    # Step 2: HR recruiter overrides candidate to Selected
    res_sel = google_drive_organizer.organize_candidate_resume(
        candidate_id="CAN-OVERRIDE-888",
        candidate_name="Pooja Ramesh",
        job_role="Data Analyst",
        status="SHORTLISTED",
        resume_file_id_or_url="mock_drive_file_999",
        parent_folder_url_or_id=SAMPLE_DRIVE_URL
    )
    assert res_sel["status_folder"] == "Selected"
    assert res_sel["relative_folder_path"] == "Selected/Data_Analyst"
