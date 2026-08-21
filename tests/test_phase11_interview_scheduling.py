import pytest
import openpyxl
import io
from fastapi.testclient import TestClient
from app.main import app
from app.services.interview_assignment_service import InterviewAssignmentService, DEFAULT_INTERVIEWERS
from app.services.time_parser_service import TimeParserService
from app.services.teams_calendar_service import TeamsCalendarService
from app.services.csv_storage import CSVStorageService

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_interviewers_fixture():
    service = InterviewAssignmentService()
    service._save_interviewers(DEFAULT_INTERVIEWERS)
    yield
    service._save_interviewers(DEFAULT_INTERVIEWERS)


def test_excel_interviewer_assignment_parser():
    service = InterviewAssignmentService()
    
    # Create sample Excel assignment sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Candidate ID", "Candidate Name", "Employee ID", "Employee Name", "Employee Email"])
    ws.append(["CAN-SHEET-001", "AKASH C", "EMP-901", "Alex Johnson", "alex.johnson@company.com"])
    
    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)

    assignments = service.parse_excel_assignments(excel_bytes.getvalue())
    assert len(assignments) == 1
    assert assignments[0]["candidate_id"] == "CAN-SHEET-001"
    assert assignments[0]["employee_name"] == "Alex Johnson"
    assert assignments[0]["employee_email"] == "alex.johnson@company.com"


def test_ai_natural_language_availability_parser():
    parser = TimeParserService()
    reply_text = "I am available tomorrow from 3:00 PM to 4:00 PM IST"

    res = parser.parse_availability_text(reply_text)
    assert res["start_time"] == "15:00"
    assert res["end_time"] == "16:00"
    assert res["display_date"] != ""
    assert "03:00 PM - 04:00 PM (IST)" in res["display_time_range"]



def test_teams_meeting_link_and_ics_generator():
    teams_service = TeamsCalendarService()
    res = teams_service.generate_teams_meeting_details(
        candidate_name="AKASH C",
        job_role="AI Engineer",
        start_datetime_iso="2026-08-18T15:00:00+05:30",
        end_datetime_iso="2026-08-18T16:00:00+05:30",
        candidate_email="akash@gmail.com",
        employee_name="Alex Johnson",
        employee_email="alex@company.com",
        hr_email="hr@company.com"
    )

    assert "teams.microsoft.com/l/meetup-join" in res["teams_join_url"]
    assert b"BEGIN:VCALENDAR" in res["ics_bytes"]
    assert b"BEGIN:VEVENT" in res["ics_bytes"]
    assert b"Technical Interview: AKASH C (AI Engineer)" in res["ics_bytes"]


def test_schedule_teams_meeting_api_endpoint(tmp_path):
    # Setup candidate record in storage
    temp_csv = str(tmp_path / "test_screening_ledger.csv")
    storage = CSVStorageService(temp_csv)
    storage.save_screening_result({
        "candidate_id": "CAN-SCHED-101",
        "candidate_name": "Deepika Rao",
        "email": "deepika@example.com",
        "job_role": "FULLSTACK_DEV",
        "status": "SHORTLISTED",
        "weighted_score": 96.5,
        "reasoning": "Selected for Full Stack Developer position."
    })

    # Call API endpoint
    response = client.post(
        "/api/v1/interviews/schedule-teams-meeting",
        json={
            "candidate_id": "CAN-SCHED-101",
            "employee_name": "Alex Johnson",
            "employee_email": "alex.johnson@company.com",
            "availability_reply_text": "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST",
            "hr_email": "hr-recruiter@company.com"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "teams_join_url" in data["schedule"]
    assert "teams.microsoft.com" in data["schedule"]["teams_join_url"]
    assert data["schedule"]["interview_status"] == "MEETING FIXED"


def test_process_email_reply_webhook():
    storage = CSVStorageService()
    storage.save_screening_result({
        "candidate_id": "CAN-SHEET-001",
        "candidate_name": "Akash C",
        "email": "akash@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "assigned_employee_id": "EMP-101",
        "assigned_employee_name": "Alex Johnson",
        "assigned_employee_email": "alex.johnson@company.com",
        "interview_status": "YET TO BE FIXED"
    })

    response = client.post(
        "/api/v1/interviews/process-email-reply",
        json={
            "employee_email": "alex.johnson@company.com",
            "employee_name": "Alex Johnson",
            "reply_body_text": "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST",
            "hr_email": "hr-recruiter@company.com"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "schedule" in data
    assert data["schedule"]["interview_status"] == "MEETING FIXED"


def test_get_interviewer_workloads():
    response = client.get("/api/v1/interviews/workloads")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert len(data["interviewers"]) >= 4
    for emp in data["interviewers"]:
        assert "employee_name" in emp
        assert "total_assigned" in emp
        assert "meetings_fixed" in emp
        assert "meetings_pending" in emp


def test_assign_candidate_interviewer():
    storage = CSVStorageService()
    storage.save_screening_result({
        "candidate_id": "CAN-SHEET-001",
        "candidate_name": "Akash C",
        "email": "akash@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED"
    })

    response = client.post(
        "/api/v1/interviews/assign-candidate",
        json={
            "candidate_id": "CAN-SHEET-001",
            "employee_id": "EMP-102",
            "employee_name": "Priya Sharma",
            "employee_email": "priya.sharma@example.com"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["candidate"]["assigned_employee_name"] == "Priya Sharma"
    assert data["candidate"]["assigned_employee_email"] == "priya.sharma@example.com"


def test_ai_skill_based_interviewer_recommendation():
    service = InterviewAssignmentService()

    # 1. Candidate with GenAI & RAG Skills -> Should recommend Alex Johnson (Lead AI Engineer)
    genai_candidate = {
        "candidate_id": "CAN-AI-GENAI",
        "candidate_name": "Akash C",
        "job_role": "AI_ENGINEER",
        "reasoning": "Selected for AI Engineer position. Strong expertise in GenAI, RAG pipelines, LangChain, and Vector Databases.",
        "form_responses": {"Specialization": "GenAI and LLM application development"}
    }

    recs_genai = service.recommend_interviewers_for_candidate(genai_candidate)
    assert len(recs_genai) > 0
    top_genai = recs_genai[0]
    assert top_genai["employee_name"] == "Alex Johnson"
    assert top_genai["is_top_match"] is True
    assert "GenAI" in top_genai["matched_skills"] or "RAG" in top_genai["matched_skills"]
    assert top_genai["match_score"] >= 80

    # 2. Candidate with Deep Learning & PyTorch -> Should recommend Dr. Vikram Seth (Principal ML Architect)
    dl_candidate = {
        "candidate_id": "CAN-AI-DL",
        "candidate_name": "Rohit Verma",
        "job_role": "AI_ENGINEER",
        "reasoning": "Candidate demonstrated hands-on experience in Deep Learning, PyTorch model training, TensorFlow, and Computer Vision.",
        "form_responses": {"Specialization": "Deep Learning and Computer Vision"}
    }

    recs_dl = service.recommend_interviewers_for_candidate(dl_candidate)
    assert len(recs_dl) > 0
    top_dl = recs_dl[0]
    assert top_dl["employee_name"] == "Dr. Vikram Seth"
    assert top_dl["is_top_match"] is True
    assert "Deep Learning" in top_dl["matched_skills"] or "PyTorch" in top_dl["matched_skills"]
    assert top_dl["match_score"] >= 80

    # 3. Candidate with React & Frontend -> Should recommend Sarah Connor (Staff Full Stack Engineer)
    frontend_candidate = {
        "candidate_id": "CAN-FS-REACT",
        "candidate_name": "Deepika Rao",
        "job_role": "FULLSTACK_DEV",
        "reasoning": "Strong in React, Next.js, TypeScript, and modern frontend architecture.",
        "form_responses": {"Tech Stack": "React, Next.js, Tailwind CSS"}
    }

    recs_fe = service.recommend_interviewers_for_candidate(frontend_candidate)
    assert len(recs_fe) > 0
    top_fe = recs_fe[0]
    assert top_fe["employee_name"] == "Sarah Connor"
    assert top_fe["is_top_match"] is True
    assert "React" in top_fe["matched_skills"] or "TypeScript" in top_fe["matched_skills"]


def test_recommendations_api_endpoint():
    storage = CSVStorageService()
    storage.save_screening_result({
        "candidate_id": "CAN-REC-001",
        "candidate_name": "Karthik R",
        "email": "karthik@example.com",
        "job_role": "AI_ENGINEER",
        "status": "SHORTLISTED",
        "weighted_score": 92.0,
        "reasoning": "Selected for AI Engineer: Extensive experience building GenAI and RAG solutions with LangChain."
    })

    # Call recommendation API
    response = client.get("/api/v1/interviews/recommendations/CAN-REC-001")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["candidate_id"] == "CAN-REC-001"
    assert data["top_recommendation"] is not None
    assert data["top_recommendation"]["employee_name"] == "Alex Johnson"
    assert data["top_recommendation"]["match_score"] >= 80
    assert len(data["recommendations"]) > 0


def test_excel_roster_upload_with_skill_set_column(tmp_path):
    temp_json = str(tmp_path / "custom_interviewers.json")
    service = InterviewAssignmentService(data_path=temp_json)

    # Create Excel sheet with explicit 'Skill Set' column
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Employee ID", "Employee Name", "Department", "Designation", "Email", "Skill Set"])
    ws.append(["EMP-801", "Dr. Alan Turing", "AI Engineer", "Chief AI Scientist", "alan@example.com", "GenAI, LLM, RAG, Transformers, Python"])
    ws.append(["EMP-802", "Ada Lovelace", "Full Stack Developer", "Principal Architect", "ada@example.com", "React, TypeScript, FastAPI, PostgreSQL"])

    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)

    imported = service.import_interviewers_from_excel_bytes(excel_bytes.getvalue(), filename="custom_roster.xlsx")
    assert len(imported) == 2
    assert imported[0]["employee_name"] == "Dr. Alan Turing"
    assert "GenAI" in imported[0]["skills"]
    assert "RAG" in imported[0]["skills"]
    assert imported[1]["employee_name"] == "Ada Lovelace"
    assert "React" in imported[1]["skills"]
    assert "FastAPI" in imported[1]["skills"]



