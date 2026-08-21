import re
import json
import email
import imaplib
import structlog
import asyncio
from email.header import decode_header
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
from app.core.config import settings
from app.services.time_parser_service import TimeParserService
from app.services.teams_calendar_service import TeamsCalendarService
from app.services.email_service import EmailService
from app.services.csv_storage import CSVStorageService

logger = structlog.get_logger(__name__)


class InboxWatcherService:
    """
    Automated Gmail IMAP Inbox Poller & AI Availability Reply Processor.
    Listens for employee reply emails, parses interview timing via AI,
    schedules MS Teams meetings, and updates candidate status to 'MEETING FIXED'.
    Includes strict deduplication to prevent repeated emails.
    """

    def __init__(self):
        self.time_parser = TimeParserService()
        self.teams_service = TeamsCalendarService()
        self.email_service = EmailService()
        self.storage_service = CSVStorageService()
        self.processed_ids_path = Path("app/data/processed_email_ids.json")
        self.processed_ids_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_processed_ids(self) -> Set[str]:
        if self.processed_ids_path.exists():
            try:
                with open(self.processed_ids_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data) if isinstance(data, list) else set()
            except Exception:
                return set()
        return set()

    def _save_processed_ids(self, ids: Set[str]):
        try:
            with open(self.processed_ids_path, "w", encoding="utf-8") as f:
                json.dump(list(ids), f, indent=2)
        except Exception as e:
            logger.warning("Failed to save processed email IDs", error=str(e))

    def sync_inbox_replies(self) -> List[Dict[str, Any]]:
        """
        Synchronously polls Gmail IMAP inbox for recent availability replies,
        processes timings, generates Teams calendar invites, and updates candidate records.
        """
        username = settings.SMTP_USERNAME
        password = settings.SMTP_PASSWORD.strip() if settings.SMTP_PASSWORD else ""

        if not username or not password:
            logger.warning("No SMTP/IMAP credentials found in config. Skipping inbox sync.")
            return []

        processed_replies = []
        processed_ids = self._load_processed_ids()
        updated_ids = set(processed_ids)

        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=12)
            mail.login(username, password)
            res, data = mail.select("INBOX", readonly=True)
            if res != "OK" or not data or not data[0]:
                mail.logout()
                return []

            total_msgs = int(data[0])
            if total_msgs <= 0:
                mail.logout()
                return []

            # Inspect latest 15 messages by sequence number
            start_seq = max(1, total_msgs - 15)
            target_ids = [str(i).encode() for i in range(start_seq, total_msgs + 1)]

            for msg_id in reversed(target_ids):
                try:
                    res, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK":
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Unique identifier for the message
                            raw_msg_id = msg.get("Message-ID", "").strip()
                            date_hdr = msg.get("Date", "").strip()
                            subject_hdr = msg.get("Subject", "").strip()
                            unique_key = raw_msg_id or f"{date_hdr}_{subject_hdr}"

                            # 🛑 Deduplication Check 1: Has this specific email message already been processed?
                            if unique_key and unique_key in updated_ids:
                                continue

                            subject_parts = decode_header(subject_hdr)
                            subject = ""
                            for s, enc in subject_parts:
                                if isinstance(s, bytes):
                                    subject += s.decode(enc or "utf-8", errors="ignore")
                                else:
                                    subject += str(s)

                            from_header = msg.get("From", "")
                            
                            # Filter for replies to Availability Requests
                            if "Availability Request" not in subject and "Interview" not in subject:
                                continue

                            # Extract plain text body
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            body = payload.decode("utf-8", errors="ignore")
                                            break
                            else:
                                payload = msg.get_payload(decode=True)
                                if payload:
                                    body = payload.decode("utf-8", errors="ignore")

                            body_clean = body.strip()
                            if not body_clean:
                                continue

                            # Remove quoted reply chain
                            lines = []
                            for line in body_clean.splitlines():
                                if line.strip().startswith(">") or "wrote:" in line.lower() or "on " in line.lower() and "wrote" in line.lower():
                                    break
                                lines.append(line)
                            reply_text = "\n".join(lines).strip()

                            if not reply_text:
                                reply_text = body_clean[:200]

                            # Check if timing intent exists (am, pm, today, tomorrow, IST, available)
                            if not any(k in reply_text.lower() for k in ["available", "pm", "am", "clock", ":", "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]):
                                continue

                            # Identify candidate
                            candidates = self.storage_service.get_all_records()
                            target_candidate = None

                            # 1. Match by name in subject
                            for c in candidates:
                                c_name = c.get("candidate_name", "").strip()
                                if c_name and c_name.lower() in subject.lower():
                                    target_candidate = c
                                    break

                            # 2. Fallback to first candidate awaiting reply
                            if not target_candidate:
                                pending = [c for c in candidates if (c.get("status") or c.get("system_decision")) == "SHORTLISTED" and c.get("interview_status") != "MEETING FIXED"]
                                if pending:
                                    target_candidate = pending[0]

                            if not target_candidate:
                                continue

                            # 🛑 Deduplication Check 2: If candidate already has meeting fixed, do not send duplicate invite!
                            curr_status = (target_candidate.get("interview_status") or "").upper()
                            if curr_status == "MEETING FIXED":
                                updated_ids.add(unique_key)
                                continue

                            candidate_id = target_candidate.get("candidate_id")
                            candidate_name = target_candidate.get("candidate_name", "Candidate")
                            candidate_email = target_candidate.get("email", "candidate@example.com")
                            job_role = (target_candidate.get("job_role", "PYTHON_DEV")).replace("_", " ").title()
                            interviewer_name = target_candidate.get("assigned_employee_name") or "Alex Johnson"
                            interviewer_email = target_candidate.get("assigned_employee_email") or username
                            hr_email = settings.HR_NOTIFICATION_EMAIL

                            # Parse timing
                            time_info = self.time_parser.parse_availability_text(reply_text)

                            # Generate Teams details & .ics calendar invite
                            teams_info = self.teams_service.generate_teams_meeting_details(
                                candidate_name=candidate_name,
                                job_role=job_role,
                                start_datetime_iso=time_info["start_datetime_iso"],
                                end_datetime_iso=time_info["end_datetime_iso"],
                                candidate_email=candidate_email,
                                employee_name=interviewer_name,
                                employee_email=interviewer_email,
                                hr_email=hr_email
                            )

                            # Dispatch calendar invite email (EXACTLY ONCE)
                            self.email_service.send_teams_interview_invite(
                                candidate_name=candidate_name,
                                candidate_email=candidate_email,
                                job_role=job_role,
                                employee_name=interviewer_name,
                                employee_email=interviewer_email,
                                hr_email=hr_email,
                                display_date=time_info["display_date"],
                                display_time_range=time_info["display_time_range"],
                                teams_join_url=teams_info["teams_join_url"],
                                ics_bytes=teams_info["ics_bytes"],
                                ics_filename=teams_info["ics_filename"]
                            )

                            # Dispatch AI Interviewer Copilot Question Kit, DOCX Sheet & Candidate Resume to Interviewer
                            try:
                                from app.services.docx_generator_service import docx_question_service
                                from app.services.resume_storage_service import resume_storage

                                docx_bytes = docx_question_service.create_docx_question_sheet(
                                    candidate_record=target_candidate,
                                    interviewer_name=interviewer_name,
                                    interview_schedule=f"{time_info['display_date']} ({time_info['display_time_range']})"
                                )
                                clean_name = (candidate_name or "Candidate").replace(" ", "_")
                                docx_filename = f"GWC_Technical_Questions_{clean_name}.docx"

                                # Retrieve candidate's actual resume file
                                resume_bytes, resume_filename = resume_storage.get_resume(candidate_id, candidate_name)

                                self.email_service.send_interview_questions_docx(
                                    employee_email=interviewer_email,
                                    employee_name=interviewer_name,
                                    candidate_record=target_candidate,
                                    docx_bytes=docx_bytes,
                                    docx_filename=docx_filename,
                                    resume_bytes=resume_bytes,
                                    resume_filename=resume_filename,
                                    teams_meeting_url=teams_info["teams_join_url"],
                                    schedule_display=f"{time_info['display_date']} ({time_info['display_time_range']})"
                                )
                                logger.info("Auto-dispatched GWC Technical Questions DOCX Sheet and Candidate Resume", to=interviewer_email, candidate=candidate_name)
                            except Exception as docx_err:
                                logger.warning("Failed to auto-dispatch docx question sheet", error=str(docx_err))


                            # Update storage
                            schedule_display = f"{time_info['display_date']} ({time_info['display_time_range']})"

                            self.storage_service.update_interview_status(
                                candidate_id=candidate_id,
                                interview_status="MEETING FIXED",
                                schedule_info=schedule_display,
                                teams_url=teams_info["teams_join_url"]
                            )


                            # Mark email as permanently processed
                            updated_ids.add(unique_key)

                            logger.info(
                                "Successfully scheduled MS Teams meeting (Email dispatched once)",
                                candidate_id=candidate_id,
                                schedule=schedule_display,
                                teams_url=teams_info["teams_join_url"]
                            )

                            processed_replies.append({
                                "candidate_id": candidate_id,
                                "candidate_name": candidate_name,
                                "interviewer_name": interviewer_name,
                                "reply_text": reply_text,
                                "schedule": schedule_display,
                                "teams_url": teams_info["teams_join_url"]
                            })

                except Exception as e:
                    logger.warning("Error inspecting message in inbox", error=str(e))
                    continue

            mail.logout()

        except Exception as e:
            logger.error("Failed to connect to Gmail IMAP inbox", error=str(e))

        finally:
            if len(updated_ids) > len(processed_ids):
                self._save_processed_ids(updated_ids)

        return processed_replies


inbox_watcher = InboxWatcherService()
