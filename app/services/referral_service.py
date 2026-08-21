import openpyxl
import io
import json
import re
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

logger = structlog.get_logger(__name__)

DEFAULT_REFERRALS = [
    {
        "candidate_email": "sneha.venkat@gmail.com",
        "candidate_name": "Sneha Venkataraman",
        "candidate_phone": "97908 12345",
        "referred_by_name": "Alex Johnson",
        "referred_by_id": "EMP-101",
        "referred_by_email": "akashchandrasekar24@gmail.com",
        "department": "AI Engineer",
        "notes": "Strong background in React & FastAPI, previously worked together on enterprise data dashboards."
    },
    {
        "candidate_email": "karthik.r@example.com",
        "candidate_name": "Karthik R",
        "candidate_phone": "+919876500001",
        "referred_by_name": "Dr. Vikram Seth",
        "referred_by_id": "EMP-105",
        "referred_by_email": "akashchandrasekar24@gmail.com",
        "department": "AI Engineer",
        "notes": "College junior with solid foundational knowledge in PyTorch and transformers."
    }
]


class ReferralService:
    """
    Manages Employee Referral registry, parses Excel referral rosters,
    cross-references candidate applications against referring employees,
    and flags AI rejections for internal referrals so HR can take discretionary action.
    """

    def __init__(self, data_path: Optional[str] = None, referral_json_path: Optional[str] = None):
        target_path = referral_json_path or data_path or "app/data/referrals.json"
        self.data_path = Path(target_path)
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.referrals = self._load_referrals()

    def _load_referrals(self) -> List[Dict[str, Any]]:
        """Loads referral records from JSON file. Defaults to DEFAULT_REFERRALS if empty/missing."""
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                logger.warning("Could not read referrals.json", error=str(e))

        return list(DEFAULT_REFERRALS)

    def _save_referrals(self, referrals: List[Dict[str, Any]]):
        """Persists referral records to JSON storage."""
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(referrals, f, indent=2)
            self.referrals = list(referrals)
        except Exception as e:
            logger.error("Failed to persist referrals.json", error=str(e))

    def clear_referrals(self):
        """Clears all registered employee referrals."""
        self._save_referrals([])
        logger.info("Cleared employee referral registry.")

    def add_or_update_referral(
        self,
        candidate_name: str,
        candidate_email: str,
        candidate_phone: str = "",
        referred_by_name: str = "",
        referred_by_id: str = "",
        referred_by_email: str = "akashchandrasekar24@gmail.com",
        department: str = "Engineering",
        notes: str = "Internal employee referral"
    ) -> Dict[str, Any]:
        """Adds or updates a referral record."""
        clean_email = candidate_email.strip().lower()
        new_record = {
            "candidate_name": candidate_name.strip(),
            "candidate_email": clean_email,
            "candidate_phone": candidate_phone.strip(),
            "referred_by_name": referred_by_name.strip(),
            "referred_by_id": referred_by_id.strip(),
            "referred_by_email": referred_by_email.strip(),
            "department": department.strip(),
            "notes": notes.strip()
        }

        updated = False
        new_list = []
        for r in self.referrals:
            if (r.get("candidate_email") or "").strip().lower() == clean_email:
                new_list.append(new_record)
                updated = True
            else:
                new_list.append(r)

        if not updated:
            new_list.append(new_record)

        self._save_referrals(new_list)
        return new_record

    def get_all_referrals(self) -> List[Dict[str, Any]]:
        """Returns all registered employee referrals."""
        return self.referrals

    def get_referral_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Finds referral record matching candidate email (case-insensitive)."""
        if not email:
            return None
        clean_email = email.strip().lower()
        for ref in self.referrals:
            if (ref.get("candidate_email") or "").strip().lower() == clean_email:
                return ref
        return None

    def get_referral_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Finds referral record matching candidate phone."""
        if not phone:
            return None
        clean_phone = re.sub(r"[^\d]", "", phone)
        if not clean_phone:
            return None
        for ref in self.referrals:
            cand_phone = re.sub(r"[^\d]", "", ref.get("candidate_phone") or "")
            if cand_phone and cand_phone == clean_phone:
                return ref
        return None

    def find_referral_match(self, candidate_record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Finds referral match by candidate email or phone."""
        email = candidate_record.get("email") or candidate_record.get("candidate_email") or ""
        match = self.get_referral_by_email(email)
        if match:
            return match

        phone = candidate_record.get("phone") or candidate_record.get("candidate_phone") or ""
        return self.get_referral_by_phone(phone)

    def cross_reference_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enriches candidate records with referring employee details and flags
        referred candidates who were rejected by AI for HR alert visibility.
        """
        enriched = []
        for c in candidates:
            c_copy = dict(c)
            ref = self.find_referral_match(c_copy)
            if ref:
                c_copy["is_referred"] = True
                c_copy["referred_by_name"] = ref.get("referred_by_name", "")
                c_copy["referred_by_id"] = ref.get("referred_by_id", "")
                c_copy["referred_by_email"] = ref.get("referred_by_email", "")
                c_copy["referral_department"] = ref.get("department", "")
                c_copy["referral_notes"] = ref.get("notes", "")

                status = (c_copy.get("status") or c_copy.get("system_decision") or "").upper()
                hr_status = (c_copy.get("hr_approval_status") or "").upper()

                if status == "REJECTED" or hr_status == "REJECTED":
                    c_copy["referral_alert"] = "REFERRED_REJECTED"
                    c_copy["referral_alert_message"] = (
                        f"⚠️ Referred by {ref.get('referred_by_name')} ({ref.get('referred_by_id')}) — "
                        f"AI Decision: REJECTED. Recruiter discretionary review recommended."
                    )
                else:
                    c_copy["referral_alert"] = "REFERRED_QUALIFIED"
                    c_copy["referral_alert_message"] = f"🌟 Referred by {ref.get('referred_by_name')} ({ref.get('referred_by_id')})"
            else:
                c_copy["is_referred"] = False
                c_copy["referred_by_name"] = ""
                c_copy["referred_by_id"] = ""
                c_copy["referred_by_email"] = ""
                c_copy["referral_department"] = ""
                c_copy["referral_notes"] = ""
                c_copy["referral_alert"] = ""
                c_copy["referral_alert_message"] = ""

            enriched.append(c_copy)
        return enriched

    def import_referrals_from_excel_bytes(
        self,
        file_bytes: bytes,
        filename: str = "employee_referrals.xlsx"
    ) -> List[Dict[str, Any]]:
        """
        Parses uploaded Excel (.xlsx/.xls) or CSV sheet of employee referrals.
        Expected columns:
        Candidate Name, Candidate Email, Candidate Phone, Referred By (Employee Name),
        Employee ID, Employee Email, Department, Notes / Relationship.
        """
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))

            if not rows or len(rows) < 2:
                raise ValueError("Excel file is empty or missing data rows.")

            raw_headers = [str(h).strip().lower() if h else "" for h in rows[0]]

            cand_name_idx = self._find_column_index(raw_headers, ["candidate name", "candidate_name", "candidate", "applicant"])
            cand_email_idx = self._find_column_index(raw_headers, ["candidate email", "candidate_email", "applicant email", "email"])
            cand_phone_idx = self._find_column_index(raw_headers, ["candidate phone", "candidate_phone", "phone", "mobile", "contact"])
            emp_name_idx = self._find_column_index(raw_headers, ["referred by", "referred_by", "employee name", "emp_name", "referrer", "referred by name"])
            emp_id_idx = self._find_column_index(raw_headers, ["employee id", "employee_id", "emp_id", "referrer id", "empid"])
            emp_email_idx = self._find_column_index(raw_headers, ["employee email", "employee_email", "referrer email", "emp_email"])
            dept_idx = self._find_column_index(raw_headers, ["department", "dept", "team", "domain"])
            notes_idx = self._find_column_index(raw_headers, ["notes", "relationship", "comments", "remarks", "note"])

            new_referrals = []
            for row_idx, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                cand_email = str(row[cand_email_idx]).strip() if cand_email_idx is not None and cand_email_idx < len(row) and row[cand_email_idx] else ""
                if not cand_email or "@" not in cand_email:
                    continue

                cand_name = str(row[cand_name_idx]).strip() if cand_name_idx is not None and cand_name_idx < len(row) and row[cand_name_idx] else "Referred Candidate"
                cand_phone = str(row[cand_phone_idx]).strip() if cand_phone_idx is not None and cand_phone_idx < len(row) and row[cand_phone_idx] else ""
                emp_name = str(row[emp_name_idx]).strip() if emp_name_idx is not None and emp_name_idx < len(row) and row[emp_name_idx] else "GWC Employee"
                emp_id = str(row[emp_id_idx]).strip() if emp_id_idx is not None and emp_id_idx < len(row) and row[emp_id_idx] else f"EMP-{row_idx:03d}"
                emp_email = str(row[emp_email_idx]).strip() if emp_email_idx is not None and emp_email_idx < len(row) and row[emp_email_idx] else "akashchandrasekar24@gmail.com"
                dept = str(row[dept_idx]).strip() if dept_idx is not None and dept_idx < len(row) and row[dept_idx] else "Engineering"
                notes = str(row[notes_idx]).strip() if notes_idx is not None and notes_idx < len(row) and row[notes_idx] else "Internal employee referral"

                new_referrals.append({
                    "candidate_email": cand_email,
                    "candidate_name": cand_name,
                    "candidate_phone": cand_phone,
                    "referred_by_name": emp_name,
                    "referred_by_id": emp_id,
                    "referred_by_email": emp_email,
                    "department": dept,
                    "notes": notes
                })

            if not new_referrals:
                raise ValueError("No valid referral records with candidate email addresses could be parsed from the file.")

            # Update registry
            self._save_referrals(new_referrals)
            logger.info("Successfully imported employee referrals from Excel", count=len(new_referrals), filename=filename)
            return new_referrals

        except Exception as e:
            logger.error("Failed to parse referral Excel upload", error=str(e))
            raise ValueError(f"Failed to parse referral file: {str(e)}")

    def generate_sample_referral_template_excel(self) -> bytes:
        """
        Generates a clean, GWC DATA.AI styled Excel template for Employee Referrals.
        Columns: Candidate Name, Candidate Email, Candidate Phone, Referred By (Employee Name),
        Employee ID, Employee Email, Department, Relationship / Notes.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Employee Referrals"

        headers = [
            "Candidate Name",
            "Candidate Email",
            "Candidate Phone",
            "Referred By (Employee Name)",
            "Employee ID",
            "Employee Email",
            "Department",
            "Relationship / Notes"
        ]
        ws.append(headers)

        # Header styling (GWC Purple background + White Bold text)
        header_fill = PatternFill(start_color="7030B1", end_color="7030B1", fill_type="solid")
        header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
        center_align = Alignment(horizontal="center", vertical="center")

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        # Sample referral entries
        sample_rows = [
            [
                "Sneha Venkataraman",
                "sneha.venkat@gmail.com",
                "97908 12345",
                "Alex Johnson",
                "EMP-101",
                "akashchandrasekar24@gmail.com",
                "AI Engineer",
                "Strong background in React & FastAPI, worked together on enterprise data dashboards."
            ],
            [
                "Karthik R",
                "karthik.r@example.com",
                "+919876500001",
                "Dr. Vikram Seth",
                "EMP-105",
                "akashchandrasekar24@gmail.com",
                "AI Engineer",
                "College junior with solid knowledge in PyTorch, transformers, and model deployment."
            ],
            [
                "Rahul Sharma",
                "rahul.sharma@example.com",
                "+919876500002",
                "Priya Sharma",
                "EMP-102",
                "akashchandrasekar24@gmail.com",
                "Full Stack Developer",
                "Senior backend engineer with strong PostgreSQL, Docker, and FastAPI microservices."
            ]
        ]

        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        for row in sample_rows:
            ws.append(row)

        for row in ws.iter_rows(min_row=2, max_row=len(sample_rows)+1, min_col=1, max_col=8):
            for cell in row:
                cell.font = Font(name="Arial", size=10)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        # Set column widths
        col_widths = [22, 28, 18, 26, 16, 28, 20, 48]
        for idx, width in enumerate(col_widths, 1):
            col_letter = openpyxl.utils.get_column_letter(idx)
            ws.column_dimensions[col_letter].width = width

        out_stream = io.BytesIO()
        wb.save(out_stream)
        out_stream.seek(0)
        return out_stream.getvalue()

    def _find_column_index(self, headers: List[str], keywords: List[str]) -> Optional[int]:
        """Helper to match column header names flexibly."""
        for idx, h in enumerate(headers):
            for kw in keywords:
                if kw in h:
                    return idx
        return None


referral_service = ReferralService()
