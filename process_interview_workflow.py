"""
Live End-to-End Interviewer Assignment & MS Teams Meeting Scheduling Script.

1. Creates & parses HR Interviewer Assignment Excel Sheet (interview_assignments.xlsx).
2. Parses natural language employee availability reply string.
3. Generates Microsoft Teams Meeting URL & .ics iCalendar invite file.
4. Dispatches formal MS Teams meeting invitation email via SMTP to Candidate, Interviewer, and HR!

Usage:
    python process_interview_workflow.py
"""

import openpyxl
import sys
import structlog
from app.services.interview_assignment_service import InterviewAssignmentService
from app.services.time_parser_service import TimeParserService
from app.services.teams_calendar_service import TeamsCalendarService
from app.services.email_service import EmailService
from app.services.csv_storage import CSVStorageService
from app.core.config import settings

# Force UTF-8 stdout encoding on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

logger = structlog.get_logger(__name__)


def run_interview_workflow():
    print("\n==================================================")
    print("[*] HR INTERVIEWER ASSIGNMENT & MS TEAMS SCHEDULER")
    print("==================================================\n")

    # 1. Create & Ingest HR Interview Assignment Excel File
    print("[1/4] Generating & Ingesting HR Interviewer Assignment Excel Sheet...")
    excel_path = "app/data/interview_assignments.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Interviewer Assignments"

    ws.append(["Candidate ID", "Candidate Name", "Employee ID", "Employee Name", "Employee Email"])
    ws.append(["CAN-SHEET-001", "AKASH C", "EMP-901", "Alex Johnson (Technical Lead)", "akashchandrasekar24@gmail.com"])
    ws.append(["CAN-LIVE-FS01", "Deepika Rao", "EMP-902", "Priya Sharma (Engineering Mgr)", "deepika.fs@example.com"])

    wb.save(excel_path)
    print(f"      [+] Saved HR Assignment Excel: {excel_path}")

    assignment_service = InterviewAssignmentService()
    assignments = assignment_service.parse_excel_assignments(excel_path)

    print(f"      [+] Parsed {len(assignments)} interviewer assignment(s) from Excel.\n")
    for a in assignments:
        print(f"      • Candidate: {a['candidate_name']} ({a['candidate_id']}) -> Interviewer: {a['employee_name']} ({a['employee_email']})")

    # 2. Simulate & Parse Employee Email Reply Availability String
    print("\n[2/4] Simulating & Parsing Employee Availability Reply Text...")
    employee_reply_text = "I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST"
    print(f"      [+] Raw Employee Email Reply: \"{employee_reply_text}\"")

    time_parser = TimeParserService()
    time_info = time_parser.parse_availability_text(employee_reply_text)

    print(f"      [+] Parsed Schedule Date : {time_info['display_date']}")
    print(f"      [+] Parsed Time Window  : {time_info['display_time_range']}")
    print(f"      [+] Start ISO Datetime  : {time_info['start_datetime_iso']}")
    print(f"      [+] End ISO Datetime    : {time_info['end_datetime_iso']}\n")

    # 3. Generate MS Teams Link & .ics Calendar Invite
    print("[3/4] Generating Microsoft Teams Meeting URL & .ics iCalendar File...")
    teams_service = TeamsCalendarService()
    
    target_assignment = assignments[0] # Akash C -> Alex Johnson
    
    teams_info = teams_service.generate_teams_meeting_details(
        candidate_name=target_assignment["candidate_name"],
        job_role="AI Engineer",
        start_datetime_iso=time_info["start_datetime_iso"],
        end_datetime_iso=time_info["end_datetime_iso"],
        candidate_email="akashchandrasekar24@gmail.com",
        employee_name=target_assignment["employee_name"],
        employee_email=target_assignment["employee_email"],
        hr_email=settings.HR_NOTIFICATION_EMAIL
    )

    print(f"      [+] MS Teams Join URL  : {teams_info['teams_join_url']}")
    print(f"      [+] iCalendar File     : {teams_info['ics_filename']} ({len(teams_info['ics_bytes'])} bytes)\n")

    # 4. Dispatch Email Invitation to Candidate, Interviewer & HR
    print("[4/4] Dispatching MS Teams Email Invitation with Calendar Attachment via SMTP...")
    email_service = EmailService()

    email_res = email_service.send_teams_interview_invite(
        candidate_name=target_assignment["candidate_name"],
        candidate_email="akashchandrasekar24@gmail.com",
        job_role="AI Engineer",
        employee_name=target_assignment["employee_name"],
        employee_email=target_assignment["employee_email"],
        hr_email=settings.HR_NOTIFICATION_EMAIL,
        display_date=time_info["display_date"],
        display_time_range=time_info["display_time_range"],
        teams_join_url=teams_info["teams_join_url"],
        ics_bytes=teams_info["ics_bytes"],
        ics_filename=teams_info["ics_filename"]
    )

    print(f"      [+] Email Delivery Status : {email_res.get('status')}")
    print(f"      [+] Recipients Invites    : {', '.join(email_res.get('recipients', []))}")
    print(f"      [+] Delivery Method       : {email_res.get('delivery_method')}")
    print(f"      [+] MS Teams Meeting Link : {email_res.get('teams_url')}\n")

    print("==================================================")
    print("[+] INTERVIEW SCHEDULING WORKFLOW COMPLETED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_interview_workflow()
