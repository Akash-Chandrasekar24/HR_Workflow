import structlog
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Response, status
from pydantic import BaseModel, Field

from app.services.interview_assignment_service import InterviewAssignmentService
from app.services.time_parser_service import TimeParserService
from app.services.teams_calendar_service import TeamsCalendarService
from app.services.email_service import EmailService
from app.services.csv_storage import CSVStorageService
from app.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/interviews", tags=["Interview Scheduling & MS Teams"])

assignment_service = InterviewAssignmentService()
time_parser = TimeParserService()
teams_service = TeamsCalendarService()
email_service = EmailService()
storage_service = CSVStorageService()


class AvailabilityParseRequest(BaseModel):
    reply_text: str = Field(..., json_schema_extra={"example": "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST"}, description="Natural language email reply string from employee/interviewer")


class ScheduleTeamsMeetingRequest(BaseModel):
    candidate_id: str = Field(..., json_schema_extra={"example": "CAN-SHEET-001"})
    candidate_name: Optional[str] = Field(None, description="Optional candidate name if not found in ledger")
    candidate_email: Optional[str] = Field(None, description="Optional candidate email if not found in ledger")
    job_role: Optional[str] = Field(None, description="Optional job role")
    employee_email: str = Field(..., json_schema_extra={"example": "employee@company.com"})
    employee_name: Optional[str] = Field("Technical Interviewer")
    availability_reply_text: str = Field(..., json_schema_extra={"example": "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST"})
    hr_email: Optional[str] = Field(None, description="HR email. Defaults to configured HR_NOTIFICATION_EMAIL if omitted.")


class AssignInterviewerRequest(BaseModel):
    candidate_id: str = Field(..., json_schema_extra={"example": "CAN-SHEET-001"})
    employee_id: str = Field(..., json_schema_extra={"example": "EMP-101"})
    employee_name: str = Field(..., json_schema_extra={"example": "Alex Johnson"})
    employee_email: str = Field(..., json_schema_extra={"example": "akashchandrasekar24@gmail.com"})


@router.get("/workloads", summary="Get Live Technical Interviewer Workloads & Capacity")
async def get_interviewer_workloads():
    """
    Computes real-time workload counts (total assigned, fixed meetings, pending meetings)
    for all technical interviewers to help HR load balance interview assignments.
    """
    try:
        candidates = storage_service.get_all_records()
        workloads = assignment_service.compute_workloads(candidates)
        return {
            "status": "SUCCESS",
            "count": len(workloads),
            "interviewers": workloads
        }
    except Exception as e:
        logger.error("Failed to compute interviewer workloads", error=str(e))
        raise HTTPException(status_code=500, detail=f"Workload computation failed: {str(e)}")


@router.get("/interviewers", summary="Get Active Interviewer Roster")
async def get_interviewers_endpoint(role: Optional[str] = None):
    """
    Returns list of active technical interviewers, optionally filtered by job role / department.
    """
    if role:
        interviewers = assignment_service.get_interviewers_for_role(role)
    else:
        interviewers = assignment_service.get_interviewers()
    return {
        "status": "SUCCESS",
        "count": len(interviewers),
        "interviewers": interviewers
    }


@router.get("/recommendations/{candidate_id}", summary="Get AI Recommended Interviewer Matches with Recommendation Scores")
async def get_interviewer_recommendations_for_candidate(candidate_id: str):
    """
    Evaluates candidate background and job requirements against active technical interviewers,
    returning ranked interviewers with AI recommendation match scores (0-100%), matched skills,
    and capacity balancing explanations.
    """
    candidate = storage_service.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate with ID '{candidate_id}' not found in records.")

    try:
        all_candidates = storage_service.get_all_records()
        recommendations = assignment_service.recommend_interviewers_for_candidate(
            candidate_record=candidate,
            candidate_records_for_workload=all_candidates
        )
        return {
            "status": "SUCCESS",
            "candidate_id": candidate_id,
            "candidate_name": candidate.get("candidate_name", "Applicant"),
            "job_role": candidate.get("job_role", ""),
            "count": len(recommendations),
            "top_recommendation": recommendations[0] if recommendations else None,
            "recommendations": recommendations
        }
    except Exception as e:
        logger.error("Failed to generate interviewer recommendations", candidate_id=candidate_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Recommendation engine error: {str(e)}")


@router.post("/upload-roster", summary="Upload Excel Sheet of Technical Interviewers & Departments")
async def upload_interviewer_roster(file: UploadFile = File(...)):
    """
    Uploads an Excel (.xlsx) file containing employee details:
    ID, Name, Department, Designation, Email.
    Updates the active interviewer roster and recalculates all live workloads.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx/.xls) or CSV files are supported.")

    try:
        file_bytes = await file.read()
        imported = assignment_service.import_interviewers_from_excel_bytes(file_bytes, filename=file.filename)
        candidates = storage_service.get_all_records()
        workloads = assignment_service.compute_workloads(candidates)

        return {
            "status": "SUCCESS",
            "message": f"Successfully uploaded and imported {len(imported)} interviewers from '{file.filename}'.",
            "count": len(imported),
            "interviewers": workloads
        }
    except Exception as e:
        logger.error("Failed to process interviewer roster upload", error=str(e))
        raise HTTPException(status_code=400, detail=f"Upload processing failed: {str(e)}")


@router.get("/template/excel", summary="Download Sample Excel Template for Interviewer Roster")
async def download_interviewer_template_excel():
    """
    Downloads a pre-formatted, GWC-branded Excel template (.xlsx) with sample employee details.
    """
    try:
        template_bytes = assignment_service.generate_sample_interviewer_template_excel()
        return Response(
            content=template_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="GWC_Interviewer_Roster_Template.xlsx"'}
        )
    except Exception as e:
        logger.error("Failed to generate interviewer template", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate template.")


@router.post("/clear-roster", summary="Clear Technical Interviewer Roster")
async def clear_interviewer_roster():
    """
    Clears the active interviewer roster so the tracker displays the empty state.
    """
    assignment_service.clear_interviewers()
    return {
        "status": "SUCCESS",
        "message": "Interviewer roster cleared successfully.",
        "interviewers": []
    }





@router.post("/assign-candidate", summary="Assign or Switch Designated Technical Interviewer for a Candidate")
async def assign_candidate_interviewer(payload: AssignInterviewerRequest):
    """
    Assigns or switches the designated technical interviewer for a candidate in the ledger.
    """
    updated = storage_service.assign_interviewer_to_candidate(
        candidate_id=payload.candidate_id,
        employee_id=payload.employee_id,
        employee_name=payload.employee_name,
        employee_email=payload.employee_email
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Candidate '{payload.candidate_id}' not found.")

    logger.info(
        "Assigned candidate to interviewer",
        candidate_id=payload.candidate_id,
        interviewer=payload.employee_name
    )

    return {
        "status": "SUCCESS",
        "message": f"Successfully assigned candidate {payload.candidate_id} to {payload.employee_name} ({payload.employee_email}).",
        "candidate": updated
    }


@router.post("/assign-and-request-availability", summary="Assign Candidate and Dispatch Availability Request Email to Interviewer")
async def assign_and_request_availability(payload: AssignInterviewerRequest):
    """
    Complete Workflow Trigger:
    1. Assigns candidate to designated interviewer in the database ledger.
    2. Sends GWC DATA.AI branded availability request email to the employee (with HR in CC).
    3. Asks employee to reply to the email with their preferred interview timings.
    """
    candidate = storage_service.get_record_by_id(payload.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{payload.candidate_id}' not found.")

    # 1. Update assignment & approve candidate
    storage_service.approve_candidate_by_hr(payload.candidate_id)
    updated = storage_service.assign_interviewer_to_candidate(
        candidate_id=payload.candidate_id,
        employee_id=payload.employee_id,
        employee_name=payload.employee_name,
        employee_email=payload.employee_email
    )

    # 2. Dispatch availability request email
    candidate_name = candidate.get("candidate_name", "Applicant")
    job_role = (candidate.get("job_role", "PYTHON_DEV")).replace("_", " ").title()
    candidate_email = candidate.get("email", "candidate@example.com")
    hr_email = settings.HR_NOTIFICATION_EMAIL

    email_res = email_service.send_interviewer_availability_request(
        candidate_name=candidate_name,
        candidate_id=payload.candidate_id,
        job_role=job_role,
        candidate_email=candidate_email,
        employee_name=payload.employee_name,
        employee_email=payload.employee_email,
        hr_email=hr_email
    )

    logger.info(
        "Dispatched availability request email to assigned interviewer",
        candidate_id=payload.candidate_id,
        employee_email=payload.employee_email,
        delivery=email_res.get("status")
    )

    return {
        "status": "SUCCESS",
        "message": f"Successfully assigned {candidate_name} to {payload.employee_name}. Availability request email dispatched to {payload.employee_email}.",
        "candidate": updated,
        "email_delivery": email_res
    }



@router.post("/ingest-assignments", summary="Upload HR Interviewer Assignment Excel File (interview_assignments.xlsx)")
async def ingest_assignments(file: UploadFile = File(...)):
    """
    Parses HR Excel assignment sheet mapping candidates to technical interviewers.
    Expected columns: Candidate ID, Candidate Name, Employee Name, Employee ID, Employee Email.
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a Microsoft Excel (.xlsx) file.")

    try:
        content = await file.read()
        assignments = assignment_service.parse_excel_assignments(content)
        
        # Save assignments to storage ledger
        for a in assignments:
            storage_service.assign_interviewer_to_candidate(
                candidate_id=a["candidate_id"],
                employee_id=a["employee_id"],
                employee_name=a["employee_name"],
                employee_email=a["employee_email"]
            )

        return {
            "status": "SUCCESS",
            "message": f"Successfully parsed and assigned {len(assignments)} interviewer assignments from {file.filename}",
            "assignments": assignments
        }
    except Exception as e:
        logger.error("Error parsing HR assignment Excel sheet", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to parse assignment Excel sheet: {str(e)}")


@router.post("/parse-availability", summary="Parse Natural Language Employee Reply Time Slot")

async def parse_employee_availability(payload: AvailabilityParseRequest):
    """
    Parses natural language employee reply text (e.g., 'Available tomorrow 3pm to 4pm IST')
    and extracts structured ISO datetimes and formatted time ranges.
    """
    try:
        parsed = time_parser.parse_availability_text(payload.reply_text)
        return {
            "status": "SUCCESS",
            "parsed": parsed
        }
    except Exception as e:
        logger.error("Failed to parse employee availability text", error=str(e))
        raise HTTPException(status_code=500, detail=f"Time slot parsing error: {str(e)}")


@router.post("/schedule-teams-meeting", summary="Schedule MS Teams Meeting & Dispatch Invites to Candidate, Employee & HR")
async def schedule_teams_meeting(payload: ScheduleTeamsMeetingRequest):
    """
    Complete End-to-End Interview Scheduling Endpoint:
    1. Look up Candidate from ledger (or use provided payload fields).
    2. Parse Employee Availability Reply String into structured Datetimes.
    3. Generate MS Teams Join URL & iCalendar (.ics) File.
    4. Dispatch Email Invitation with Teams link and .ics attachment to Candidate, Employee & HR.
    """
    # 1. Lookup candidate
    candidate = storage_service.get_record_by_id(payload.candidate_id) or {}
    
    candidate_name = payload.candidate_name or candidate.get("candidate_name") or "Candidate"
    candidate_email = payload.candidate_email or candidate.get("email") or "candidate@example.com"
    raw_role = payload.job_role or candidate.get("job_role", "PYTHON_DEV")
    job_role = raw_role.replace("_", " ").title()
    hr_email = payload.hr_email or settings.HR_NOTIFICATION_EMAIL

    try:
        # 2. Parse time slot
        time_info = time_parser.parse_availability_text(payload.availability_reply_text)

        # 3. Generate MS Teams link & .ics calendar invite
        teams_info = teams_service.generate_teams_meeting_details(
            candidate_name=candidate_name,
            job_role=job_role,
            start_datetime_iso=time_info["start_datetime_iso"],
            end_datetime_iso=time_info["end_datetime_iso"],
            candidate_email=candidate_email,
            employee_name=payload.employee_name,
            employee_email=payload.employee_email,
            hr_email=hr_email
        )

        # 4. Dispatch Email Invite with Teams link & .ics attachment
        email_res = email_service.send_teams_interview_invite(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_role=job_role,
            employee_name=payload.employee_name,
            employee_email=payload.employee_email,
            hr_email=hr_email,
            display_date=time_info["display_date"],
            display_time_range=time_info["display_time_range"],
            teams_join_url=teams_info["teams_join_url"],
            ics_bytes=teams_info["ics_bytes"],
            ics_filename=teams_info["ics_filename"]
        )

        # 5. Automatically generate & dispatch Interviewer Copilot Question Kit Briefing to the interviewer
        try:
            from app.services.question_generator_service import question_generator
            question_kit = question_generator.generate_question_kit(candidate)
            email_service.send_interviewer_copilot_briefing(
                employee_email=payload.employee_email,
                employee_name=payload.employee_name,
                candidate_record=candidate,
                question_kit=question_kit,
                teams_meeting_url=teams_info["teams_join_url"],
                schedule_display=f"{time_info['display_date']} ({time_info['display_time_range']})"
            )
            logger.info("Dispatched Interviewer Copilot Briefing to assigned interviewer", interviewer=payload.employee_email, candidate=candidate_name)
        except Exception as q_err:
            logger.warning("Failed to auto-dispatch copilot question kit", error=str(q_err))

        # 6. Automatically update candidate interview status in CSV & Excel storage
        schedule_display = f"{time_info['display_date']} ({time_info['display_time_range']})"
        storage_service.update_interview_status(
            candidate_id=payload.candidate_id,
            interview_status="MEETING FIXED",
            schedule_info=schedule_display,
            teams_url=teams_info["teams_join_url"]
        )

        logger.info(
            "Updated candidate interview status to MEETING FIXED",
            candidate_id=payload.candidate_id,
            schedule=schedule_display
        )

        return {
            "status": "SUCCESS",
            "message": f"Successfully scheduled MS Teams meeting, dispatched invites and sent Interviewer Copilot Question Kit to {payload.employee_name}.",
            "candidate": {"id": payload.candidate_id, "name": candidate_name, "email": candidate_email},
            "interviewer": {"name": payload.employee_name, "email": payload.employee_email},
            "schedule": {
                "date": time_info["display_date"],
                "time_range": time_info["display_time_range"],
                "teams_join_url": teams_info["teams_join_url"],
                "interview_status": "MEETING FIXED"
            },
            "delivery_details": email_res
        }


    except Exception as e:
        logger.error("Failed to schedule MS Teams meeting", error=str(e))
        raise HTTPException(status_code=500, detail=f"Interview scheduling failed: {str(e)}")


class EmailReplyWebhookRequest(BaseModel):
    employee_email: str = Field(..., description="Email address of the employee/interviewer")
    employee_name: Optional[str] = Field("Technical Interviewer", description="Name of the employee/interviewer")
    candidate_id: Optional[str] = Field(None, description="Candidate ID if referenced in email subject or thread")
    reply_body_text: str = Field(..., description="Raw text of the email reply from employee containing availability timings")
    hr_email: Optional[str] = Field(None, description="HR email")


@router.post("/process-email-reply", summary="Automated Background Email Reply Ingestion & Scheduling")
async def process_email_reply_webhook(payload: EmailReplyWebhookRequest):
    """
    Automated background processor for employee email replies:
    1. Detects candidate from candidate_id or finds first pending candidate assigned.
    2. Parses availability timings from raw reply_body_text using AI/NLP.
    3. Blocks MS Teams calendar, creates meeting URL, and emails invitations.
    4. Automatically flips candidate status to 'MEETING FIXED'.
    """
    candidate_id = payload.candidate_id
    if not candidate_id:
        # Find first shortlisted candidate yet to be fixed
        shortlisted = storage_service.get_shortlisted_records()
        pending = [c for c in shortlisted if c.get("interview_status") != "MEETING FIXED"]
        if pending:
            candidate_id = pending[0].get("candidate_id")
        elif shortlisted:
            candidate_id = shortlisted[0].get("candidate_id")
        else:
            raise HTTPException(status_code=404, detail="No shortlisted candidate found to schedule.")

    schedule_req = ScheduleTeamsMeetingRequest(
        candidate_id=candidate_id,
        employee_email=payload.employee_email,
        employee_name=payload.employee_name or "Technical Interviewer",
        availability_reply_text=payload.reply_body_text,
        hr_email=payload.hr_email
    )
    return await schedule_teams_meeting(schedule_req)


@router.post("/sync-inbox-replies", summary="Sync & Process Unread Availability Reply Emails from Gmail Inbox")
async def sync_inbox_replies_endpoint():
    """
    Connects to Gmail IMAP, checks for recent employee availability replies,
    extracts timings with AI, schedules Teams meetings, and updates candidate status to 'MEETING FIXED'.
    """
    from app.services.inbox_watcher_service import inbox_watcher
    
    results = inbox_watcher.sync_inbox_replies()
    return {
        "status": "SUCCESS",
        "processed_count": len(results),
        "details": results
    }


@router.get("/recommendations/{candidate_id}", summary="Get AI-Recommended Technical Interviewers for Candidate based on Skill Set")
async def get_candidate_interviewer_recommendations(candidate_id: str):
    """
    Analyzes candidate's technical skills, applied role, and screening reasoning,
    and matches them against the active technical interviewer roster's specialized skill sets.
    Returns ranked interviewers with match percentage, matched skills, and recommendation reasons.
    """
    candidate = storage_service.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")

    all_candidates = storage_service.get_all_records()
    recommendations = assignment_service.recommend_interviewers_for_candidate(
        candidate_record=candidate,
        candidate_records_for_workload=all_candidates
    )

    top_match = recommendations[0] if recommendations else None

    return {
        "status": "SUCCESS",
        "candidate_id": candidate_id,
        "candidate_name": candidate.get("candidate_name", "Applicant"),
        "job_role": candidate.get("job_role", "PYTHON_DEV"),
        "top_recommendation": top_match,
        "recommendations": recommendations
    }


@router.get("/question-kit/{candidate_id}", summary="Get AI Interviewer Copilot Question Kit for Candidate")
async def get_candidate_question_kit(candidate_id: str):
    """
    Returns the tailored technical interview question kit based on the candidate's resume and screening score.
    """
    candidate = storage_service.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")

    from app.services.question_generator_service import question_generator
    question_kit = question_generator.generate_question_kit(candidate)

    return {
        "status": "SUCCESS",
        "candidate_id": candidate_id,
        "question_kit": question_kit
    }


class SendQuestionKitRequest(BaseModel):
    candidate_id: str = Field(..., description="Candidate ID")
    employee_email: Optional[str] = Field(None, description="Interviewer email (defaults to assigned)")


@router.post("/send-question-kit", summary="Manually Email Interviewer Copilot Question Kit to Interviewer")
async def send_question_kit_to_interviewer(payload: SendQuestionKitRequest):
    """
    Generates and emails the AI Interviewer Copilot Question Kit directly to the assigned interviewer.
    """
    candidate = storage_service.get_record_by_id(payload.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{payload.candidate_id}' not found.")

    interviewer_email = payload.employee_email or candidate.get("assigned_employee_email") or settings.HR_NOTIFICATION_EMAIL
    interviewer_name = candidate.get("assigned_employee_name") or "Technical Interviewer"

    from app.services.question_generator_service import question_generator
    question_kit = question_generator.generate_question_kit(candidate)

    res = email_service.send_interviewer_copilot_briefing(
        employee_email=interviewer_email,
        employee_name=interviewer_name,
        candidate_record=candidate,
        question_kit=question_kit,
        teams_meeting_url=candidate.get("teams_meeting_url"),
        schedule_display=candidate.get("interview_schedule")
    )

    return {
        "status": "SUCCESS",
        "message": f"Successfully dispatched AI Interviewer Copilot Question Kit to {interviewer_email}.",
        "delivery": res,
        "question_kit": question_kit
    }


@router.get("/download-questions-docx/{candidate_id}", summary="Download GWC-Branded Word Document (.docx) of 10 Technical Questions")
async def download_questions_docx(candidate_id: str):
    """
    Generates and downloads the official GWC DATA.AI styled Word document (.docx)
    containing 10 tailored technical questions based on the candidate's resume.
    """
    candidate = storage_service.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")

    from app.services.docx_generator_service import docx_question_service
    interviewer_name = candidate.get("assigned_employee_name") or "Technical Interviewer"
    docx_bytes = docx_question_service.create_docx_question_sheet(
        candidate_record=candidate,
        interviewer_name=interviewer_name
    )

    clean_name = (candidate.get("candidate_name") or "Candidate").replace(" ", "_")
    filename = f"GWC_Technical_Questions_{clean_name}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


class SendDocxRequest(BaseModel):
    candidate_id: str = Field(..., description="Candidate ID")
    employee_email: Optional[str] = Field(None, description="Interviewer email (defaults to assigned)")


@router.post("/send-questions-docx", summary="Email GWC-Branded 10-Question Word Document (.docx) to Assigned Interviewer")
async def send_questions_docx_to_interviewer(payload: SendDocxRequest):
    """
    Generates the GWC-branded Word document (.docx) with 10 resume-based technical questions
    and emails it directly to the assigned interviewer.
    """
    candidate = storage_service.get_record_by_id(payload.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail=f"Candidate '{payload.candidate_id}' not found.")

    interviewer_email = payload.employee_email or candidate.get("assigned_employee_email") or settings.HR_NOTIFICATION_EMAIL
    interviewer_name = candidate.get("assigned_employee_name") or "Technical Interviewer"

    from app.services.docx_generator_service import docx_question_service
    from app.services.resume_storage_service import resume_storage

    docx_bytes = docx_question_service.create_docx_question_sheet(
        candidate_record=candidate,
        interviewer_name=interviewer_name,
        interview_schedule=candidate.get("interview_schedule")
    )

    clean_name = (candidate.get("candidate_name") or "Candidate").replace(" ", "_")
    docx_filename = f"GWC_Technical_Questions_{clean_name}.docx"

    # Retrieve candidate's actual resume file
    resume_bytes, resume_filename = resume_storage.get_resume(payload.candidate_id, candidate.get("candidate_name"))

    res = email_service.send_interview_questions_docx(
        employee_email=interviewer_email,
        employee_name=interviewer_name,
        candidate_record=candidate,
        docx_bytes=docx_bytes,
        docx_filename=docx_filename,
        resume_bytes=resume_bytes,
        resume_filename=resume_filename,
        teams_meeting_url=candidate.get("teams_meeting_url"),
        schedule_display=candidate.get("interview_schedule")
    )

    return {
        "status": "SUCCESS",
        "message": f"Successfully emailed GWC Technical Questions document ({docx_filename}) and Candidate Resume ({resume_filename}) to {interviewer_email}.",
        "delivery": res,
        "filename": docx_filename,
        "resume_filename": resume_filename
    }





