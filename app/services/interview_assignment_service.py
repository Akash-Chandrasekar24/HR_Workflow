import openpyxl
import io
import json
import re
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

logger = structlog.get_logger(__name__)

DEFAULT_INTERVIEWERS = [
    {
        "employee_id": "EMP-101",
        "employee_name": "Alex Johnson",
        "role": "Lead AI Engineer",
        "department": "AI Engineer",
        "domain": "AI_ENGINEER",
        "domain_label": "AI / ML Engineering",
        "skills": ["GenAI", "LLM", "RAG", "LangChain", "Prompt Engineering", "Python", "Vector Databases", "vLLM"],
        "employee_email": "akashchandrasekar24@gmail.com"
    },
    {
        "employee_id": "EMP-105",
        "employee_name": "Dr. Vikram Seth",
        "role": "Principal ML Architect",
        "department": "AI Engineer",
        "domain": "AI_ENGINEER",
        "domain_label": "AI / ML Engineering",
        "skills": ["Deep Learning", "Machine Learning", "PyTorch", "TensorFlow", "Computer Vision", "NLP", "Model Fine-Tuning", "MLOps"],
        "employee_email": "akashchandrasekar24@gmail.com"
    },
    {
        "employee_id": "EMP-102",
        "employee_name": "Priya Sharma",
        "role": "Senior Backend Lead",
        "department": "Full Stack Developer",
        "domain": "FULLSTACK_DEV",
        "domain_label": "Full Stack & Web",
        "skills": ["FastAPI", "Python", "Node.js", "PostgreSQL", "System Design", "Microservices", "Docker", "REST APIs"],
        "employee_email": "akashchandrasekar24@gmail.com"
    },
    {
        "employee_id": "EMP-104",
        "employee_name": "Sarah Connor",
        "role": "Staff Full Stack Engineer",
        "department": "Full Stack Developer",
        "domain": "FULLSTACK_DEV",
        "domain_label": "Full Stack & Web",
        "skills": ["React", "Next.js", "TypeScript", "JavaScript", "Frontend Architecture", "GraphQL", "Tailwind CSS", "Redux"],
        "employee_email": "akashchandrasekar24@gmail.com"
    },
    {
        "employee_id": "EMP-103",
        "employee_name": "Rahul Verma",
        "role": "Principal Data Architect",
        "department": "Data Analyst",
        "domain": "DATA_ANALYST",
        "domain_label": "Data Analytics & BI",
        "skills": ["Data Warehousing", "SQL", "ETL Pipelines", "Snowflake", "Databricks", "Data Modeling", "Big Data", "PostgreSQL"],
        "employee_email": "akashchandrasekar24@gmail.com"
    },
    {
        "employee_id": "EMP-106",
        "employee_name": "Ananya Iyer",
        "role": "Senior BI & Analytics Lead",
        "department": "Data Analyst",
        "domain": "DATA_ANALYST",
        "domain_label": "Data Analytics & BI",
        "skills": ["PowerBI", "Tableau", "Dashboarding", "Statistical Analysis", "Business Metrics", "SQL", "Excel", "Data Storytelling"],
        "employee_email": "akashchandrasekar24@gmail.com"
    }
]


class InterviewAssignmentService:
    """
    Parses and manages Technical Interviewer rosters from Excel/CSV uploads,
    computes live Interviewer Workload distribution metrics, and provides an
    AI-driven skill-matching recommendation engine to match candidates to the best technical interviewers.
    """

    def __init__(self, data_path: str = "app/data/interviewers.json"):
        self.data_path = Path(data_path)
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.interviewers = self._load_interviewers()

    def _load_interviewers(self) -> List[Dict[str, Any]]:
        """Loads interviewer roster from JSON storage. Defaults to empty list if no roster uploaded."""
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                logger.warning("Could not read interviewers.json", error=str(e))
        
        return []

    def _save_interviewers(self, interviewers: List[Dict[str, Any]]):
        """Persists interviewer roster to JSON file."""
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(interviewers, f, indent=2)
            self.interviewers = list(interviewers)
        except Exception as e:
            logger.error("Failed to persist interviewers", error=str(e))

    def clear_interviewers(self):
        """Clears the interviewer roster to empty."""
        self._save_interviewers([])
        logger.info("Cleared interviewer roster.")

    def get_interviewers(self) -> List[Dict[str, Any]]:
        """Returns list of all active technical interviewers."""
        return self.interviewers

    def get_interviewers_for_role(self, job_role: str) -> List[Dict[str, Any]]:
        """Filters technical interviewers specialized in the specified candidate job role / department."""
        if not job_role:
            return self.interviewers
        
        role_upper = job_role.upper()
        if "AI" in role_upper or "ML" in role_upper or "LEARNING" in role_upper:
            target_domain = "AI_ENGINEER"
        elif "DATA" in role_upper or "ANALYST" in role_upper or "BI" in role_upper:
            target_domain = "DATA_ANALYST"
        else:
            target_domain = "FULLSTACK_DEV"

        matched = [emp for emp in self.interviewers if emp.get("domain") == target_domain]
        return matched if matched else self.interviewers

    def compute_workloads(self, candidate_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Computes live workload counts (total assigned, fixed meetings, pending meetings)
        for every technical interviewer based on the candidate database.
        """
        workload_map = {}
        for emp in self.interviewers:
            emp_id = emp.get("employee_id") or f"EMP-{len(workload_map)+1}"
            workload_map[emp_id] = {
                **emp,
                "skills": emp.get("skills", []),
                "total_assigned": 0,
                "meetings_fixed": 0,
                "meetings_pending": 0,
                "assigned_candidates": []
            }

        for c in candidate_records:
            status = (c.get("status") or c.get("system_decision") or "").upper()
            if status != "SHORTLISTED":
                continue

            assigned_id = c.get("assigned_employee_id")
            assigned_name = (c.get("assigned_employee_name") or "").strip().lower()
            assigned_email = (c.get("assigned_employee_email") or "").strip().lower()

            target_entry = None
            if assigned_id and assigned_id in workload_map:
                target_entry = workload_map[assigned_id]
            elif assigned_name:
                for entry in workload_map.values():
                    if entry.get("employee_name", "").strip().lower() == assigned_name:
                        target_entry = entry
                        break
            elif assigned_email:
                for entry in workload_map.values():
                    if entry.get("employee_email", "").strip().lower() == assigned_email:
                        target_entry = entry
                        break

            if target_entry:
                target_entry["total_assigned"] += 1
                is_fixed = (c.get("interview_status") or "").upper() == "MEETING FIXED"
                if is_fixed:
                    target_entry["meetings_fixed"] += 1
                else:
                    target_entry["meetings_pending"] += 1

                target_entry["assigned_candidates"].append({
                    "candidate_id": c.get("candidate_id"),
                    "candidate_name": c.get("candidate_name"),
                    "job_role": c.get("job_role"),
                    "interview_status": "MEETING FIXED" if is_fixed else "YET TO BE FIXED"
                })

        return list(workload_map.values())

    def recommend_interviewers_for_candidate(
        self,
        candidate_record: Dict[str, Any],
        candidate_records_for_workload: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        AI & Skill-Based Interviewer Recommendation Engine powered by Google Gemini (LLM):
        Analyzes candidate skills, projects, and role, and prompts Gemini to evaluate
        and match against the active technical interviewer roster, balancing live workload capacity.
        """
        if not self.interviewers:
            return []

        # Compute live workloads
        workloads = self.compute_workloads(candidate_records_for_workload or [])

        # Call Gemini LLM Recommender (with automatic heuristic fallback)
        from app.services.interview_recommendation_service import gemini_recommender
        return gemini_recommender.recommend(
            candidate_record=candidate_record,
            interviewers_with_workload=workloads
        )

    # Alias for method compatibility
    recommend_interviewers = recommend_interviewers_for_candidate

    def import_interviewers_from_excel_bytes(self, file_bytes: bytes, filename: str = "interviewers.xlsx") -> List[Dict[str, Any]]:
        """
        Parses an uploaded Excel (.xlsx) or CSV file containing employee details:
        Expected columns: Employee ID, Employee Name, Department, Designation, Email, Skill Set (Optional).
        Updates the active interviewer roster and persists it.
        """
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))

            if not rows or len(rows) < 2:
                raise ValueError("Excel file is empty or missing data rows.")

            raw_headers = [str(h).strip().lower() if h else "" for h in rows[0]]

            id_idx = self._find_column_index(raw_headers, ["id", "emp_id", "employee_id", "employee id", "empid"])
            name_idx = self._find_column_index(raw_headers, ["name", "employee name", "employee_name", "emp_name"])
            dept_idx = self._find_column_index(raw_headers, ["department", "dept", "domain", "field", "tech"])
            role_idx = self._find_column_index(raw_headers, ["role", "designation", "title", "position"])
            email_idx = self._find_column_index(raw_headers, ["email", "employee email", "employee_email", "mail"])
            skills_idx = self._find_column_index(raw_headers, ["skill set", "skill_set", "skills", "specialization", "skills set", "tech stack", "expertise", "primary skills"])

            new_interviewers = []

            for row_idx, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                emp_id = str(row[id_idx]).strip() if id_idx is not None and id_idx < len(row) and row[id_idx] else f"EMP-{row_idx:03d}"
                emp_name = str(row[name_idx]).strip() if name_idx is not None and name_idx < len(row) and row[name_idx] else f"Interviewer {row_idx}"
                raw_dept = str(row[dept_idx]).strip() if dept_idx is not None and dept_idx < len(row) and row[dept_idx] else "AI Engineer"
                emp_role = str(row[role_idx]).strip() if role_idx is not None and role_idx < len(row) and row[role_idx] else raw_dept
                emp_email = str(row[email_idx]).strip() if email_idx is not None and email_idx < len(row) and row[email_idx] else "akashchandrasekar24@gmail.com"

                # Parse Skill Set column if present
                raw_skills_val = str(row[skills_idx]).strip() if skills_idx is not None and skills_idx < len(row) and row[skills_idx] else ""
                
                # Normalize department / domain
                dept_upper = raw_dept.upper()
                if "AI" in dept_upper or "ML" in dept_upper or "INTELLIGENCE" in dept_upper or "GENAI" in dept_upper:
                    domain = "AI_ENGINEER"
                    domain_label = "AI / ML Engineering"
                    dept_clean = "AI Engineer"
                    default_skills = ["Python", "Machine Learning", "Deep Learning", "PyTorch", "GenAI", "LLM", "RAG"]
                elif "DATA" in dept_upper or "ANALYST" in dept_upper or "BI" in dept_upper or "ANALYTICS" in dept_upper:
                    domain = "DATA_ANALYST"
                    domain_label = "Data Analytics & BI"
                    dept_clean = "Data Analyst"
                    default_skills = ["SQL", "PowerBI", "Tableau", "Data Warehousing", "ETL", "Statistical Analysis"]
                else:
                    domain = "FULLSTACK_DEV"
                    domain_label = "Full Stack & Web"
                    dept_clean = "Full Stack Developer"
                    default_skills = ["React", "TypeScript", "Node.js", "Python", "FastAPI", "PostgreSQL", "REST APIs"]

                if raw_skills_val:
                    parsed_skills = [s.strip() for s in re.split(r"[,;|/]", raw_skills_val) if s.strip()]
                else:
                    parsed_skills = default_skills

                new_interviewers.append({
                    "employee_id": emp_id,
                    "employee_name": emp_name,
                    "department": dept_clean,
                    "role": emp_role,
                    "domain": domain,
                    "domain_label": domain_label,
                    "skills": parsed_skills,
                    "employee_email": emp_email
                })

            if not new_interviewers:
                raise ValueError("No valid employee rows could be parsed from the uploaded Excel file.")

            # Save and update active roster
            self._save_interviewers(new_interviewers)
            logger.info("Successfully imported interviewer roster with skill sets from Excel", count=len(new_interviewers), filename=filename)
            return new_interviewers

        except Exception as e:
            logger.error("Failed to parse interviewer Excel upload", error=str(e))
            raise ValueError(f"Failed to parse Excel file: {str(e)}")

    def parse_excel_assignments(self, file_content_or_path: Any) -> List[Dict[str, Any]]:
        """
        Parses HR Excel assignment sheet mapping candidates to technical interviewers.
        Expected columns: Candidate ID, Candidate Name, Employee Name, Employee ID, Employee Email.
        """
        if isinstance(file_content_or_path, str):
            with open(file_content_or_path, "rb") as f:
                file_bytes = f.read()
        elif isinstance(file_content_or_path, bytes):
            file_bytes = file_content_or_path
        else:
            file_bytes = bytes(file_content_or_path)

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if not rows or len(rows) < 2:
            return []

        raw_headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        cand_id_idx = self._find_column_index(raw_headers, ["candidate id", "candidate_id", "cand_id"])
        cand_name_idx = self._find_column_index(raw_headers, ["candidate name", "candidate_name", "candidate"])
        emp_id_idx = self._find_column_index(raw_headers, ["employee id", "employee_id", "emp_id"])
        emp_name_idx = self._find_column_index(raw_headers, ["employee name", "employee_name", "interviewer"])
        emp_email_idx = self._find_column_index(raw_headers, ["employee email", "employee_email", "email", "mail"])

        assignments = []
        for r in rows[1:]:
            if not any(r):
                continue
            assignments.append({
                "candidate_id": str(r[cand_id_idx]).strip() if cand_id_idx is not None and cand_id_idx < len(r) and r[cand_id_idx] else "",
                "candidate_name": str(r[cand_name_idx]).strip() if cand_name_idx is not None and cand_name_idx < len(r) and r[cand_name_idx] else "",
                "employee_id": str(r[emp_id_idx]).strip() if emp_id_idx is not None and emp_id_idx < len(r) and r[emp_id_idx] else "",
                "employee_name": str(r[emp_name_idx]).strip() if emp_name_idx is not None and emp_name_idx < len(r) and r[emp_name_idx] else "",
                "employee_email": str(r[emp_email_idx]).strip() if emp_email_idx is not None and emp_email_idx < len(r) and r[emp_email_idx] else ""
            })
        return assignments

    def generate_sample_interviewer_template_excel(self) -> bytes:
        """
        Generates a clean, GWC-styled sample Excel template for employee details upload.
        Columns: Employee ID, Employee Name, Department, Designation, Email, Skill Set.
        """
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Employee Roster"

        headers = ["Employee ID", "Employee Name", "Department", "Designation", "Email", "Skill Set"]
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

        # Sample rows with clear Skill Set column
        sample_rows = [
            ["EMP-101", "Alex Johnson", "AI Engineer", "Lead AI Engineer", "akashchandrasekar24@gmail.com", "GenAI, LLM, RAG, LangChain, Python, Vector Databases"],
            ["EMP-105", "Dr. Vikram Seth", "AI Engineer", "Principal ML Architect", "akashchandrasekar24@gmail.com", "Deep Learning, PyTorch, TensorFlow, Computer Vision, MLOps, NLP"],
            ["EMP-102", "Priya Sharma", "Full Stack Developer", "Senior Backend Lead", "akashchandrasekar24@gmail.com", "FastAPI, Python, Node.js, PostgreSQL, System Design, Docker"],
            ["EMP-104", "Sarah Connor", "Full Stack Developer", "Staff Full Stack Engineer", "akashchandrasekar24@gmail.com", "React, Next.js, TypeScript, Frontend Architecture, GraphQL, Tailwind"],
            ["EMP-103", "Rahul Verma", "Data Analyst", "Principal Data Architect", "akashchandrasekar24@gmail.com", "SQL, Data Warehousing, ETL Pipelines, Snowflake, Data Modeling"],
            ["EMP-106", "Ananya Iyer", "Data Analyst", "Senior BI & Analytics Lead", "akashchandrasekar24@gmail.com", "PowerBI, Tableau, Statistical Analysis, Business Metrics, SQL"]
        ]

        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        for row in sample_rows:
            ws.append(row)

        for row in ws.iter_rows(min_row=2, max_row=len(sample_rows)+1, min_col=1, max_col=6):
            for cell in row:
                cell.font = Font(name="Arial", size=10)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        # Set column widths
        col_widths = [16, 22, 22, 26, 32, 48]
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


interview_assignment_service = InterviewAssignmentService()

