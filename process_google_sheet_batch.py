"""
Batch Import & Screening Script for Live Google Spreadsheet & Drive Candidates.

Downloads candidate form responses directly from your Google Spreadsheet:
https://docs.google.com/spreadsheets/d/1ADbUgOVNNCAxFhZGpTxnOpHtmIeSF6MkMMyeI55ABQk/edit

Downloads candidate resumes directly from Google Drive HTTP export links,
evaluates mandatory criteria & weighted scores, generates decision reasoning,
persists records to CSV and Excel ledgers, and dispatches the HR shortlist email digest!

Usage:
    python process_google_sheet_batch.py
"""

import argparse
import csv
import io
import re
import sys
import httpx
import structlog
from app.schemas.application import ApplicationIngestRequest
from app.services.resume_processor import ResumeProcessorService
from app.services.csv_storage import CSVStorageService
from app.services.email_service import EmailService
from app.core.config import settings
from app.core.logging_config import setup_enterprise_logging

# Initialize Enterprise Logging for Batch Runner
setup_enterprise_logging()

# Force UTF-8 stdout encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


logger = structlog.get_logger(__name__)


def extract_spreadsheet_id(url_or_id: str) -> str:
    """Extracts 44-character Google Spreadsheet ID from URL or raw ID string."""
    if not url_or_id:
        return settings.GOOGLE_SPREADSHEET_ID
    match = re.search(r"[-\w]{25,}", url_or_id)
    return match.group(0) if match else url_or_id.strip()


def extract_gid(url_or_gid: str = None) -> str:
    """Extracts GID parameter from URL (e.g. #gid=1147998574 or ?gid=1147998574) or defaults to '0'."""
    if not url_or_gid:
        return settings.GOOGLE_SPREADSHEET_GID or "0"
    match = re.search(r"[?&#]gid=(\d+)", str(url_or_gid))
    if match:
        return match.group(1)
    if str(url_or_gid).isdigit():
        return str(url_or_gid)
    return settings.GOOGLE_SPREADSHEET_GID or "0"


def extract_drive_file_id(url_or_id: str) -> str:
    """Extracts Google Drive File ID from URL or raw string."""
    if not url_or_id:
        return ""
    match = re.search(r"[-\w]{25,}", url_or_id)
    return match.group(0) if match else url_or_id.strip()


def process_spreadsheet(spreadsheet_url_or_id: str = None, gid: str = None, drive_folder_url: str = None):
    target_url_or_id = spreadsheet_url_or_id or settings.GOOGLE_SPREADSHEET_URL
    spreadsheet_id = extract_spreadsheet_id(target_url_or_id)
    target_gid = gid or extract_gid(target_url_or_id)

    export_csv_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={target_gid}"

    print(f"\n==================================================")
    print(f"[*] Fetching Candidate Data from Google Spreadsheet")
    print(f"Spreadsheet ID : {spreadsheet_id}")
    print(f"Sheet Tab GID  : {target_gid}")
    print(f"Spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={target_gid}")
    if drive_folder_url:
        print(f"Target Drive Folder: {drive_folder_url}")
    print(f"==================================================\n")


    try:
        with httpx.Client(follow_redirects=True, timeout=20.0) as client:
            response = client.get(export_csv_url)
            if response.status_code != 200:
                print(f"[!] Failed to fetch spreadsheet CSV (HTTP {response.status_code}).")
                print("    Ensure the Google Spreadsheet link access is set to 'Anyone with the link can view'.")
                return


            csv_text = response.text

    except Exception as e:
        print(f"[!] Network error accessing Google Spreadsheet: {str(e)}")
        return

    # Parse CSV content
    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)
    rows = list(reader)

    print(f"[+] Downloaded {len(rows)} candidate submission row(s) from Google Spreadsheet.\n")

    processor = ResumeProcessorService()
    storage = CSVStorageService()
    # Reset ledger so it strictly contains only current live spreadsheet records
    storage.clear_ledger()

    from app.services.google_drive_organizer import google_drive_organizer

    success_count = 0


    for idx, row in enumerate(rows, start=1):
        # Flexible field lookup
        full_name = "Applicant"
        email = "applicant@example.com"
        phone = ""
        location = ""
        job_role = "PYTHON_DEV"
        resume_url = ""
        timestamp = ""

        form_responses = {}

        for k, v in row.items():
            if not k:
                continue
            k_lower = k.lower().strip()
            v_str = str(v).strip()
            form_responses[k] = v_str

            if "name" in k_lower: full_name = v_str
            elif "email" in k_lower or "mail" in k_lower: email = v_str
            elif "phone" in k_lower or "contact" in k_lower: phone = v_str
            elif "location" in k_lower or "city" in k_lower: location = v_str
            elif "role" in k_lower or "position" in k_lower or "apply" in k_lower: job_role = v_str
            elif "timestamp" in k_lower: timestamp = v_str
            elif "resume" in k_lower or "cv" in k_lower or "upload" in k_lower or "file" in k_lower or "drive" in k_lower:
                resume_url = v_str

        file_id = extract_drive_file_id(resume_url)

        if not file_id:
            print(f"[-] Row {idx} ({full_name}): Skipping - No resume Drive file URL found.")
            continue

        candidate_id = f"CAN-SHEET-{idx:03d}"

        print(f"[*] Processing Candidate [{idx}/{len(rows)}]: {full_name} ({email}) | Role: {job_role}")

        payload = ApplicationIngestRequest(
            candidate_id=candidate_id,
            timestamp=timestamp,
            full_name=full_name,
            email=email,
            phone=phone,
            location=location,
            job_role=job_role,
            years_of_experience=0.0,
            resume_file_id=file_id,
            form_response_id=f"ROW-{idx}",
            form_responses=form_responses
        )

        result = processor.process_application(payload)
        success_count += 1

        print(f"   ↳ Score: {result.get('weighted_score')}/100 | Decision: {result.get('system_decision')}")
        print(f"   ↳ Reason: {result.get('decision_reason')}\n")

    print("==================================================")
    print(f"[+] Batch Screening Complete: {success_count}/{len(rows)} candidate(s) screened and evaluated in candidate pool.")
    print(f"[+] Staged for HR review. Drive folder relocation, CSV cooking, and email notifications are staged.")
    print(f"[+] Open the HR Command Center at http://127.0.0.1:8000/hr-portal to review, assign interviewers, and click 'Finalize Recruitment Batch'.\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch process candidates from Google Spreadsheet.")
    parser.add_argument("--url", help="Google Spreadsheet URL (e.g. https://docs.google.com/spreadsheets/d/ID/edit)", default=None)
    parser.add_argument("--gid", help="Sheet tab GID (default: 1147998574)", default=None)
    parser.add_argument("--drive-folder", help="Google Drive Target Folder URL", default=None)
    args = parser.parse_args()

    process_spreadsheet(spreadsheet_url_or_id=args.url, gid=args.gid, drive_folder_url=args.drive_folder)


