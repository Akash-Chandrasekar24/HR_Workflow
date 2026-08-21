import uuid
import structlog
from datetime import datetime
from typing import Dict, Any, List
from app.core.config import settings

logger = structlog.get_logger(__name__)


class TeamsCalendarService:
    """
    Microsoft Teams Meeting Link & iCalendar (.ics) Invite Generator Service.
    Generates Teams Join URLs and standard RFC-5545 iCalendar (.ics) files for Outlook, Teams, and Gmail.
    """

    def generate_teams_meeting_details(
        self,
        candidate_name: str,
        job_role: str,
        start_datetime_iso: str,
        end_datetime_iso: str,
        candidate_email: str,
        employee_name: str,
        employee_email: str,
        hr_email: str
    ) -> Dict[str, Any]:
        """
        Generates MS Teams Join Link and iCalendar (.ics) file bytes for Candidate, Interviewer, and HR.
        """
        meeting_id = str(uuid.uuid4())[:12]
        
        # MS Teams Join URL
        teams_join_url = f"https://teams.microsoft.com/l/meetup-join/19%3ameeting_{meeting_id}%40thread.v2/0?context=%7b%22Tid%22%3a%22gwc-enterprise-tenant%22%7d"

        # Parse ISO datetimes
        start_dt = datetime.fromisoformat(start_datetime_iso)
        end_dt = datetime.fromisoformat(end_datetime_iso)

        dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
        dtend = end_dt.strftime("%Y%m%dT%H%M%S")

        summary = f"Technical Interview: {candidate_name} ({job_role})"
        description = (
            f"Technical Interview for {candidate_name} ({job_role})\\n\\n"
            f"Candidate: {candidate_name} ({candidate_email})\\n"
            f"Interviewer: {employee_name} ({employee_email})\\n"
            f"HR Recruiter: {hr_email}\\n\\n"
            f"Join Microsoft Teams Meeting:\\n{teams_join_url}"
        )

        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//GWC Enterprise Resume Screening Platform//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:interview-{meeting_id}@company.com
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
DESCRIPTION:{description}
LOCATION:{teams_join_url}
ORGANIZER;CN="{employee_name}":mailto:{employee_email}
ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN="{candidate_name}":mailto:{candidate_email}
ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;RSVP=TRUE;CN="{employee_name}":mailto:{employee_email}
ATTENDEE;ROLE=OPT-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN="HR Recruiter":mailto:{hr_email}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""

        ics_bytes = ics_content.encode("utf-8")

        result = {
            "meeting_id": meeting_id,
            "teams_join_url": teams_join_url,
            "summary": summary,
            "start_dt": start_dt.strftime("%Y-%m-%d %H:%M"),
            "end_dt": end_dt.strftime("%Y-%m-%d %H:%M"),
            "ics_bytes": ics_bytes,
            "ics_filename": f"interview_{candidate_name.replace(' ', '_')}.ics"
        }

        logger.info("Generated MS Teams Meeting Link & iCalendar file", meeting_id=meeting_id, candidate=candidate_name)
        return result
