import csv
import json
import os
import time
import structlog
from datetime import datetime
from pathlib import Path
from filelock import FileLock
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = structlog.get_logger(__name__)

# Simplified, clean column list requested by user
CSV_HEADERS = [
    "date",
    "candidate_id",
    "candidate_name",
    "email",
    "phone",
    "job_role",
    "status",
    "weightage_score",
    "reasoning",
    "assigned_employee_id",
    "assigned_employee_name",
    "assigned_employee_email",
    "interview_status",
    "interview_schedule",
    "teams_meeting_url",
    "hr_approval_status",
    "hr_feedback",
    "hr_override_status",
    "hr_recruiter_notes",
    "referred_by_name",
    "referred_by_id",
    "referred_by_email",
    "resume_file"
]




class CSVStorageService:
    """
    Thread-Safe Clean CSV & Excel Data Ledger with 2-Phase Staging & Cooking.
    Manages active candidate review in candidate pool staging and cooks the official screening_results.csv
    and .xlsx ONLY upon explicit batch finalization by HR.
    """

    def __init__(self, csv_path: str = None):
        self.csv_path = settings.csv_absolute_path if not csv_path else Path(csv_path)
        self.xlsx_path = self.csv_path.with_suffix(".xlsx")
        self.pool_path = self.csv_path.parent / "candidates_pool.json"
        self.status_path = self.csv_path.parent / "batch_status.json"
        self.lock_path = self.csv_path.with_suffix(".lock")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Initializes storage directories and pool files."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.csv_path.exists():
            try:
                with FileLock(str(self.lock_path)):
                    with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(CSV_HEADERS)
            except Exception as e:
                logger.warning("Could not create initial CSV header file", error=str(e))

        if not self.pool_path.exists():
            records = []
            if self.csv_path.exists():
                try:
                    with open(self.csv_path, "r", encoding="utf-8") as f:
                        records = list(csv.DictReader(f))
                except Exception:
                    records = []
            self._save_pool_unlocked(records)


    def is_batch_finalized(self) -> bool:
        """Checks if the recruitment batch has been officially finalized by HR."""
        if not self.status_path.exists():
            return False
        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("is_finalized", False))
        except Exception:
            return False

    def get_batch_status(self) -> Dict[str, Any]:
        """Returns batch finalization metadata."""
        if not self.status_path.exists():
            return {"is_finalized": False, "finalized_at": None, "finalized_count": 0}
        try:
            with open(self.status_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"is_finalized": False, "finalized_at": None, "finalized_count": 0}

    def set_batch_status(self, is_finalized: bool, details: Dict[str, Any] = None):
        """Sets batch finalization status."""
        data = details or {}
        data["is_finalized"] = is_finalized
        data["updated_at"] = datetime.now().isoformat()
        with open(self.status_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _read_pool_unlocked(self) -> List[Dict[str, Any]]:
        """Reads candidate pool from JSON staging."""
        if not self.pool_path.exists():
            return []
        try:
            with open(self.pool_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_pool_unlocked(self, records: List[Dict[str, Any]]):
        """Saves candidate pool to JSON staging."""
        try:
            with open(self.pool_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.warning("Could not save candidate pool", error=str(e))

    def clear_ledger(self):
        """Resets the candidate pool and removes pre-cooked files."""
        with FileLock(str(self.lock_path)):
            self._save_pool_unlocked([])
            self.set_batch_status(False)
            if self.csv_path.exists():
                try:
                    self.csv_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if self.xlsx_path.exists():
                try:
                    self.xlsx_path.unlink(missing_ok=True)
                except Exception:
                    pass
            logger.info("Cleared candidate pool and ledger for fresh recruitment cycle", path=str(self.csv_path))

    def cook_final_csv_ledger(self) -> Dict[str, Any]:
        """
        Officially prepares, compiles, and writes the finalized screening_results.csv
        and screening_results.xlsx from the candidate pool after HR completes all reviews.
        """
        with FileLock(str(self.lock_path)):
            records = self._read_pool_unlocked()
            
            # Format and normalize rows for CSV
            cooked_rows = []
            for r in records:
                cand_date = r.get("date") or r.get("screening_date") or datetime.now().strftime("%Y-%m-%d")
                res_id = r.get("resume_file") or r.get("resume_file_id") or r.get("resume_url") or ""
                if res_id and not str(res_id).startswith("http"):
                    res_link = f"https://drive.google.com/file/d/{res_id}/view"
                else:
                    res_link = str(res_id)

                row = {
                    "date": cand_date,
                    "candidate_id": r.get("candidate_id", ""),
                    "candidate_name": r.get("candidate_name", "Applicant"),
                    "email": r.get("email", ""),
                    "phone": r.get("phone", ""),
                    "job_role": r.get("job_role", ""),
                    "status": r.get("status") or r.get("system_decision") or "REJECTED",
                    "weightage_score": str(r.get("weightage_score", r.get("weighted_score", "0.0"))),
                    "reasoning": r.get("reasoning", r.get("decision_reason", "")),
                    "assigned_employee_id": r.get("assigned_employee_id", ""),
                    "assigned_employee_name": r.get("assigned_employee_name", ""),
                    "assigned_employee_email": r.get("assigned_employee_email", ""),
                    "interview_status": r.get("interview_status", "UNASSIGNED"),
                    "interview_schedule": r.get("interview_schedule", ""),
                    "teams_meeting_url": r.get("teams_meeting_url", ""),
                    "hr_approval_status": r.get("hr_approval_status", "PENDING_HR_APPROVAL"),
                    "hr_feedback": r.get("hr_feedback", ""),
                    "hr_override_status": r.get("hr_override_status", r.get("hr_override_decision", "")),
                    "hr_recruiter_notes": r.get("hr_recruiter_notes", r.get("hr_override_reason", "")),
                    "referred_by_name": r.get("referred_by_name", ""),
                    "referred_by_id": r.get("referred_by_id", ""),
                    "referred_by_email": r.get("referred_by_email", ""),
                    "resume_file": res_link
                }
                cooked_rows.append(row)

            # Write finalized CSV file
            for attempt in range(3):
                try:
                    with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                        writer.writeheader()
                        writer.writerows(cooked_rows)
                    break
                except PermissionError:
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning("Error writing cooked CSV file", error=str(e))
                    break

            # Export Excel ledger
            self._export_to_excel_unlocked(cooked_rows)

            logger.info("Successfully cooked official CSV & Excel ledger on batch finalization", count=len(cooked_rows), csv_path=str(self.csv_path))
            return {
                "status": "SUCCESS",
                "count": len(cooked_rows),
                "csv_path": str(self.csv_path),
                "xlsx_path": str(self.xlsx_path),
                "records": cooked_rows
            }


    def save_screening_result(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Appends or updates candidate screening record in clean CSV and Excel sheet.
        """
        with FileLock(str(self.lock_path)):
            existing_records = self._read_all_unlocked()
            
            candidate_id = record.get("candidate_id", "")
            
            # Determine final status (Explicit status or HR override or system decision)
            status = record.get("status") or record.get("hr_override_decision") or record.get("system_decision") or "REJECTED"
            weightage_score = str(record.get("weightage_score") if record.get("weightage_score") is not None else record.get("weighted_score", 0.0))
            reasoning = record.get("reasoning") or record.get("decision_reason") or ""
            
            # Human in loop approval status & 90%+ AI Auto-Acceptance
            hr_approval_status = record.get("hr_approval_status")
            try:
                num_score = float(weightage_score)
            except (ValueError, TypeError):
                num_score = 0.0

            auto_accept_threshold = getattr(settings, "AI_AUTO_ACCEPT_THRESHOLD", 90.0)

            if not hr_approval_status:
                if status == "SHORTLISTED" and num_score >= auto_accept_threshold:
                    # 90%+ AI Score Auto-Acceptance
                    hr_approval_status = "HR_APPROVED"
                elif status in ["SHORTLISTED", "HR_REVIEW"]:
                    hr_approval_status = "PENDING_HR_APPROVAL"
                elif status == "REJECTED":
                    hr_approval_status = "REJECTED"
                else:
                    hr_approval_status = "PENDING_HR_APPROVAL"

            hr_feedback = record.get("hr_feedback", "")

            # Default interview status
            interview_status = record.get("interview_status")
            if not interview_status:
                interview_status = "UNASSIGNED" if status == "SHORTLISTED" else "N/A"

            # Assigned employee: Only populated when HR explicitly assigns
            emp_id = record.get("assigned_employee_id") or record.get("employee_id") or ""
            emp_name = record.get("assigned_employee_name") or record.get("employee_name") or ""
            emp_email = record.get("assigned_employee_email") or record.get("employee_email") or ""


            # Build Google Drive resume link from file ID
            resume_file_id = record.get("resume_file", "") or record.get("resume_file_id", "") or record.get("resume_url", "")
            if resume_file_id and not resume_file_id.startswith("http"):
                resume_file_link = f"https://drive.google.com/file/d/{resume_file_id}/view"
            else:
                resume_file_link = resume_file_id  # Already a full URL

            # Screening date: preserve existing or set to today
            cand_date = record.get("date", "") or record.get("screening_date", "") or datetime.now().strftime("%Y-%m-%d")

            row_dict = {
                "date": cand_date,
                "candidate_id": candidate_id,
                "candidate_name": record.get("candidate_name", "Applicant"),
                "email": record.get("email", ""),
                "phone": record.get("phone", ""),
                "job_role": record.get("job_role", "PYTHON_DEV"),
                "status": status,
                "weightage_score": weightage_score,
                "reasoning": reasoning,
                "assigned_employee_id": emp_id,
                "assigned_employee_name": emp_name,
                "assigned_employee_email": emp_email,
                "interview_status": interview_status,
                "interview_schedule": record.get("interview_schedule", ""),
                "teams_meeting_url": record.get("teams_meeting_url", ""),
                "hr_approval_status": hr_approval_status,
                "hr_feedback": hr_feedback,
                "hr_override_status": record.get("hr_override_decision", record.get("hr_override_status", "")),
                "hr_recruiter_notes": record.get("hr_override_reason", record.get("hr_recruiter_notes", "")),
                "referred_by_name": record.get("referred_by_name", ""),
                "referred_by_id": record.get("referred_by_id", ""),
                "referred_by_email": record.get("referred_by_email", ""),
                "resume_file": resume_file_link
            }




            # Replace or append in candidate pool
            updated = False
            for i, r in enumerate(existing_records):
                if r.get("candidate_id") == candidate_id:
                    existing_records[i] = row_dict
                    updated = True
                    break

            if not updated:
                existing_records.append(row_dict)

            # Persist to candidate pool staging
            self._save_pool_unlocked(existing_records)

            # If batch is already finalized, update CSV & Excel synchronously
            if self.is_batch_finalized() or self.csv_path.exists():
                for attempt in range(3):
                    try:
                        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                            writer.writeheader()
                            writer.writerows(existing_records)
                        self._export_to_excel_unlocked(existing_records)
                        break
                    except PermissionError:
                        time.sleep(0.3)
                    except Exception as e:
                        logger.warning("Error writing CSV file", error=str(e))
                        break

            logger.info("Persisted candidate screening result to candidate pool", candidate_id=candidate_id, status=status)

            
            # Return enriched dict for internal pipeline callers & tests
            res_dict = dict(row_dict)
            res_dict["system_decision"] = status
            res_dict["weighted_score"] = float(weightage_score) if weightage_score else 0.0
            res_dict["decision_reason"] = reasoning
            res_dict["mandatory_passed"] = record.get("mandatory_passed", True)
            res_dict["hr_override_decision"] = row_dict["hr_override_status"]
            res_dict["hr_override_reason"] = row_dict["hr_recruiter_notes"]
            res_dict["processing_status"] = record.get("processing_status", "COMPLETED")
            return res_dict

    def save_hr_override(
        self,
        candidate_id: str,
        override_decision: str,
        override_reason: str
    ) -> Optional[Dict[str, Any]]:
        """Logs HR recruiter decision override."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["hr_override_decision"] = override_decision.upper()
        candidate["hr_override_reason"] = override_reason
        candidate["status"] = override_decision.upper()

        return self.save_screening_result(candidate)

    def get_all_records(self) -> List[Dict[str, Any]]:
        """Retrieves all candidate records from CSV ledger."""
        with FileLock(str(self.lock_path)):
            return self._read_all_unlocked()

    def get_shortlisted_records(self) -> List[Dict[str, Any]]:
        """Retrieves only SHORTLISTED candidate records from CSV ledger."""
        all_records = self.get_all_records()
        return [r for r in all_records if (r.get("status") or r.get("system_decision")) == "SHORTLISTED"]

    def assign_interviewer_to_candidate(
        self,
        candidate_id: str,
        employee_id: str,
        employee_name: str,
        employee_email: str
    ) -> Optional[Dict[str, Any]]:
        """Assigns or reassigns a technical interviewer to a candidate."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["assigned_employee_id"] = employee_id
        candidate["assigned_employee_name"] = employee_name
        candidate["assigned_employee_email"] = employee_email

        return self.save_screening_result(candidate)

    def update_interview_status(
        self,
        candidate_id: str,
        interview_status: str,
        schedule_info: str = "",
        teams_url: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Updates interview booking status for a candidate."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["interview_status"] = interview_status
        if schedule_info:
            candidate["interview_schedule"] = schedule_info
        if teams_url:
            candidate["teams_meeting_url"] = teams_url

        return self.save_screening_result(candidate)




    def bulk_approve_candidates(self, candidate_ids: Optional[List[str]] = None, approve_all_pending: bool = False) -> List[Dict[str, Any]]:
        """
        Approves multiple candidates at once in Human-in-the-Loop review.
        Performs atomic update on the CSV and Excel ledgers.
        """
        with FileLock(str(self.lock_path)):
            existing = self._read_all_unlocked()
            target_ids = set(candidate_ids or [])
            approved_records = []

            for r in existing:
                cid = r.get("candidate_id")
                curr_status = (r.get("hr_approval_status") or "").upper()

                match = False
                if approve_all_pending and curr_status in ["PENDING_HR_APPROVAL", "", "RE_EVALUATED"] and (r.get("status") or "").upper() in ["SHORTLISTED", "HR_REVIEW"]:
                    match = True
                elif candidate_ids and cid in target_ids:
                    match = True

                if match:
                    r["hr_approval_status"] = "HR_APPROVED"
                    r["status"] = "SHORTLISTED"
                    r["system_decision"] = "SHORTLISTED"
                    r["hr_override_status"] = "HR_APPROVED"
                    r["hr_override_decision"] = "HR_APPROVED"
                    if not r.get("interview_status") or r.get("interview_status") == "N/A":
                        r["interview_status"] = "UNASSIGNED"
                    approved_records.append(r)

            if approved_records:
                for attempt in range(3):
                    try:
                        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                            writer.writeheader()
                            writer.writerows(existing)
                        self._export_to_excel_unlocked(existing)
                        break
                    except PermissionError:
                        time.sleep(0.3)
                    except Exception as e:
                        logger.warning("Could not write CSV in bulk approval", error=str(e))
                        break

            logger.info("Executed bulk HR candidate approval", count=len(approved_records))
            return approved_records

    def bulk_reject_candidates(self, candidate_ids: List[str], reason: str = "") -> List[Dict[str, Any]]:
        """
        Rejects multiple candidates at once in Human-in-the-Loop review.
        """
        with FileLock(str(self.lock_path)):
            existing = self._read_all_unlocked()
            target_ids = set(candidate_ids or [])
            rejected_records = []

            for r in existing:
                cid = r.get("candidate_id")
                if cid in target_ids:
                    r["hr_approval_status"] = "REJECTED_BY_HR"
                    r["status"] = "REJECTED"
                    r["system_decision"] = "REJECTED"
                    r["hr_override_status"] = "REJECTED_BY_HR"
                    r["hr_override_decision"] = "REJECTED"
                    r["hr_recruiter_notes"] = reason or "Bulk rejected during HR review."
                    r["hr_override_reason"] = reason or "Bulk rejected during HR review."
                    r["interview_status"] = "N/A"
                    rejected_records.append(r)

            if rejected_records:
                for attempt in range(3):
                    try:
                        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                            writer.writeheader()
                            writer.writerows(existing)
                        self._export_to_excel_unlocked(existing)
                        break
                    except PermissionError:
                        time.sleep(0.3)
                    except Exception as e:
                        logger.warning("Could not write CSV in bulk rejection", error=str(e))
                        break

            logger.info("Executed bulk HR candidate rejection", count=len(rejected_records))
            return rejected_records

    def approve_candidate_by_hr(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Approves candidate in Human-in-the-Loop review, enabling interview assignment."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["hr_approval_status"] = "HR_APPROVED"
        candidate["status"] = "SHORTLISTED"
        candidate["system_decision"] = "SHORTLISTED"
        candidate["hr_override_status"] = "HR_APPROVED"
        candidate["hr_override_decision"] = "HR_APPROVED"
        candidate["interview_status"] = "UNASSIGNED"
        return self.save_screening_result(candidate)

    def reject_candidate_by_hr(self, candidate_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        """Rejects candidate in Human-in-the-Loop review."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["hr_approval_status"] = "REJECTED_BY_HR"
        candidate["status"] = "REJECTED"
        candidate["system_decision"] = "REJECTED"
        candidate["hr_override_status"] = "REJECTED_BY_HR"
        candidate["hr_override_decision"] = "REJECTED"
        candidate["hr_recruiter_notes"] = reason or "Rejected during HR review."
        candidate["hr_override_reason"] = reason or "Rejected during HR review."
        candidate["interview_status"] = "N/A"
        return self.save_screening_result(candidate)

    def update_candidate_re_evaluation(
        self,
        candidate_id: str,
        new_score: float,
        new_reason: str,
        hr_feedback: str,
        new_status: str = "SHORTLISTED"
    ) -> Optional[Dict[str, Any]]:
        """Updates candidate with AI re-evaluation results based on HR feedback."""
        candidate = self.get_record_by_id(candidate_id)
        if not candidate:
            return None

        candidate["weightage_score"] = str(round(new_score, 2))
        candidate["weighted_score"] = float(round(new_score, 2))
        candidate["reasoning"] = new_reason
        candidate["decision_reason"] = new_reason
        candidate["hr_feedback"] = hr_feedback
        candidate["hr_approval_status"] = "RE_EVALUATED"
        candidate["status"] = new_status
        candidate["system_decision"] = new_status
        return self.save_screening_result(candidate)

    def get_record_by_id(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Finds candidate record by candidate_id."""
        records = self.get_all_records()
        for r in records:
            if r.get("candidate_id") == candidate_id:
                res = dict(r)
                try:
                    res["weighted_score"] = float(res.get("weightage_score", res.get("weighted_score", 0.0)))
                except (ValueError, TypeError):
                    res["weighted_score"] = 0.0
                res["system_decision"] = res.get("status", "REJECTED")
                res["decision_reason"] = res.get("reasoning", "")
                res["mandatory_passed"] = res.get("status") in ["SHORTLISTED", "HR_REVIEW"]
                res["hr_override_decision"] = res.get("hr_override_status", "")
                res["hr_override_reason"] = res.get("hr_recruiter_notes", "")
                res["hr_approval_status"] = res.get("hr_approval_status") or ("PENDING_HR_APPROVAL" if res.get("status") in ["SHORTLISTED", "HR_REVIEW"] else "REJECTED")
                res["hr_feedback"] = res.get("hr_feedback", "")
                res["processing_status"] = "COMPLETED"
                return res
        return None

    def list_candidates(self, job_role: Optional[str] = None, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias method for list_applications API and tests."""
        records = self.get_all_records()
        if job_role and job_role.upper() != "ALL":
            records = [r for r in records if r.get("job_role", "").upper() == job_role.upper()]
        if search_query:
            sq = search_query.lower()
            records = [
                r for r in records
                if sq in r.get("candidate_name", "").lower()
                or sq in r.get("email", "").lower()
                or sq in r.get("candidate_id", "").lower()
            ]
        return records

    # Alias for get_record_by_id
    get_candidate = get_record_by_id

    def _read_all_unlocked(self) -> List[Dict[str, Any]]:
        """Internal helper to read candidate records from pool staging or CSV."""
        pool_recs = self._read_pool_unlocked()
        if pool_recs:
            from app.services.referral_service import referral_service
            return referral_service.cross_reference_candidates(pool_recs)

        if not self.csv_path.exists():
            return []
        try:
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                raw_records = list(reader)
            
            # Cross-reference with active employee referrals
            from app.services.referral_service import referral_service
            return referral_service.cross_reference_candidates(raw_records)
        except Exception:
            return []


    def _export_to_excel_unlocked(self, records: List[Dict[str, Any]]):
        """Generates clean Excel (.xlsx) file with strictly requested candidate details, status, weightage score, and reasoning."""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Candidate Screening Summary"

            # Clean header styling
            header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            border_thin = Border(
                left=Side(style='thin', color='D9D9D9'),
                right=Side(style='thin', color='D9D9D9'),
                top=Side(style='thin', color='D9D9D9'),
                bottom=Side(style='thin', color='D9D9D9')
            )

            headers = [
                "Date",
                "Candidate ID",
                "Candidate Name",
                "Email",
                "Phone",
                "Applied Job Role",
                "Status",
                "Weightage Score (0-100)",
                "Selection Reasoning",
                "HR Override Status",
                "HR Recruiter Notes",
                "Resume Drive Link"
            ]

            ws.append(headers)

            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            ws.row_dimensions[1].height = 28

            # Data rows
            for row_idx, r in enumerate(records, start=2):
                dec = r.get("status") or r.get("system_decision") or "REJECTED"
                
                try:
                    score_float = float(r.get("weightage_score", r.get("weighted_score", 0.0)))
                except (ValueError, TypeError):
                    score_float = 0.0

                resume_link = r.get("resume_file") or r.get("resume_file_id") or ""
                if resume_link and not str(resume_link).startswith("http"):
                    resume_link = f"https://drive.google.com/file/d/{resume_link}/view"

                row_vals = [
                    r.get("date") or r.get("screening_date") or datetime.now().strftime("%Y-%m-%d"),
                    r.get("candidate_id", ""),
                    r.get("candidate_name", ""),
                    r.get("email", ""),
                    r.get("phone", ""),
                    r.get("job_role", ""),
                    dec,
                    score_float,
                    r.get("reasoning", r.get("decision_reason", "")),
                    r.get("hr_override_status", r.get("hr_override_decision", "")),
                    r.get("hr_recruiter_notes", r.get("hr_override_reason", "")),
                    resume_link
                ]

                ws.append(row_vals)
                ws.row_dimensions[row_idx].height = 42

                # Highlight Status column (Column 7)
                status_cell = ws.cell(row=row_idx, column=7)
                status_cell.alignment = Alignment(horizontal="center", vertical="center")
                
                if dec == "SHORTLISTED":
                    status_cell.fill = PatternFill(start_color="E2EFDA", fill_type="solid") # Soft Green
                    status_cell.font = Font(bold=True, color="375623")
                elif dec == "HR_REVIEW":
                    status_cell.fill = PatternFill(start_color="FFF2CC", fill_type="solid") # Soft Yellow
                    status_cell.font = Font(bold=True, color="7F6000")
                else:
                    status_cell.fill = PatternFill(start_color="FCE4D6", fill_type="solid") # Soft Red
                    status_cell.font = Font(bold=True, color="C65911")

                # Format borders and text wrapping
                for c_idx in range(1, len(row_vals) + 1):
                    c = ws.cell(row=row_idx, column=c_idx)
                    c.border = border_thin
                    if c_idx in [9, 11]: # Wrap text for reasoning & notes
                        c.alignment = Alignment(vertical="center", wrap_text=True)

            # Adjust column widths cleanly
            col_widths = [14, 16, 22, 25, 16, 18, 16, 22, 65, 20, 30, 45]
            for i, w in enumerate(col_widths, start=1):
                col_letter = openpyxl.utils.get_column_letter(i)
                ws.column_dimensions[col_letter].width = w

            for attempt in range(3):
                try:
                    wb.save(self.xlsx_path)
                    break
                except PermissionError:
                    time.sleep(0.3)
                except Exception:
                    break

            logger.info("Successfully updated clean Excel spreadsheet ledger", path=str(self.xlsx_path))

        except Exception as e:
            logger.warning("Could not export Excel file (.xlsx)", error=str(e))

    def generate_excel_bytes(self, records: List[Dict[str, Any]]) -> bytes:
        """
        Generates in-memory Microsoft Excel (.xlsx) bytes stream.
        Guarantees clean, standard OpenXML spreadsheet format for direct browser download.
        """
        import io
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Candidate Screening Summary"

        header_fill = PatternFill(start_color="7030B1", end_color="7030B1", fill_type="solid") # GWC Purple
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )

        headers = [
            "Date",
            "Candidate ID",
            "Candidate Name",
            "Email",
            "Phone",
            "Applied Job Role",
            "Status",
            "Weightage Score (0-100)",
            "Selection Reasoning",
            "Assigned Interviewer",
            "Interview Status",
            "Teams Meeting Link",
            "Resume Drive Link"
        ]

        ws.append(headers)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.row_dimensions[1].height = 28

        for row_idx, r in enumerate(records, start=2):
            dec = r.get("status") or r.get("system_decision") or "REJECTED"
            
            try:
                score_float = float(r.get("weightage_score", r.get("weighted_score", 0.0)))
            except (ValueError, TypeError):
                score_float = 0.0

            interviewer_info = r.get("assigned_employee_name", "")
            if r.get("assigned_employee_email"):
                interviewer_info += f" ({r.get('assigned_employee_email')})"

            resume_link = r.get("resume_file") or r.get("resume_file_id") or ""
            if resume_link and not str(resume_link).startswith("http"):
                resume_link = f"https://drive.google.com/file/d/{resume_link}/view"

            row_vals = [
                r.get("date") or r.get("screening_date") or datetime.now().strftime("%Y-%m-%d"),
                r.get("candidate_id", ""),
                r.get("candidate_name", ""),
                r.get("email", ""),
                r.get("phone", ""),
                (r.get("job_role", "")).replace("_", " "),
                dec,
                score_float,
                r.get("reasoning", r.get("decision_reason", "")),
                interviewer_info,
                r.get("interview_status", "YET TO BE FIXED"),
                r.get("teams_meeting_url", ""),
                resume_link
            ]

            ws.append(row_vals)
            ws.row_dimensions[row_idx].height = 36

            status_cell = ws.cell(row=row_idx, column=7)
            status_cell.alignment = Alignment(horizontal="center", vertical="center")
            if dec == "SHORTLISTED":
                status_cell.fill = PatternFill(start_color="E2EFDA", fill_type="solid")
                status_cell.font = Font(bold=True, color="375623")
            elif dec == "HR_REVIEW":
                status_cell.fill = PatternFill(start_color="FFF2CC", fill_type="solid")
                status_cell.font = Font(bold=True, color="7F6000")
            else:
                status_cell.fill = PatternFill(start_color="FCE4D6", fill_type="solid")

                status_cell.font = Font(bold=True, color="C65911")

            for c_idx in range(1, len(row_vals) + 1):
                c = ws.cell(row=row_idx, column=c_idx)
                c.border = border_thin
                if c_idx in [8]:
                    c.alignment = Alignment(vertical="center", wrap_text=True)

        col_widths = [16, 22, 25, 16, 20, 16, 22, 60, 28, 20, 35]
        for i, w in enumerate(col_widths, start=1):
            col_letter = openpyxl.utils.get_column_letter(i)
            ws.column_dimensions[col_letter].width = w

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.getvalue()

