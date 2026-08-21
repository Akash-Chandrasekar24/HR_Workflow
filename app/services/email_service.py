import os
import smtplib
import structlog
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.config import settings

logger = structlog.get_logger(__name__)


class EmailService:
    """
    Automated HR Email Notification Service with GWC Data.AI Branding & MS Teams Calendar Invites.
    """

    def __init__(
        self,
        smtp_server: str = None,
        smtp_port: int = None,
        username: str = None,
        password: str = None,
        sender_email: str = None
    ):
        self.smtp_server = smtp_server or settings.SMTP_SERVER
        self.smtp_port = smtp_port or settings.SMTP_PORT
        self.username = username or settings.SMTP_USERNAME
        self.password = password or settings.SMTP_PASSWORD
        self.sender_email = sender_email or settings.SENDER_EMAIL or self.username or "noreply@company.com"

    def send_shortlist_digest(
        self,
        recipient_email: str,
        candidates: List[Dict[str, Any]],
        csv_attachment_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Builds and sends executive HR digest email with shortlisted candidate reasoning and CSV attachment.
        """
        recipient = recipient_email or settings.HR_NOTIFICATION_EMAIL

        total_count = len(candidates)
        shortlisted = [c for c in candidates if (c.get("status") or c.get("system_decision")) == "SHORTLISTED"]
        review_count = len([c for c in candidates if (c.get("status") or c.get("system_decision")) == "HR_REVIEW"])
        rejected_count = len([c for c in candidates if (c.get("status") or c.get("system_decision")) == "REJECTED"])

        shortlisted_count = len(shortlisted)
        timestamp_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")

        subject = f"📋 Candidate Screening Digest: {shortlisted_count} Shortlisted out of {total_count} Applicants ({timestamp_str})"

        html_body = self._build_html_email_template(
            total_count=total_count,
            shortlisted_count=shortlisted_count,
            review_count=review_count,
            rejected_count=rejected_count,
            shortlisted_candidates=shortlisted,
            timestamp_str=timestamp_str
        )

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = recipient
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        attached_filename = None
        if csv_attachment_path:
            csv_file = Path(csv_attachment_path)
            if csv_file.exists():
                try:
                    with open(csv_file, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    attached_filename = csv_file.name
                    part.add_header("Content-Disposition", f"attachment; filename={attached_filename}")
                    msg.attach(part)
                except Exception as e:
                    logger.warning("Could not attach CSV file to email", error=str(e))

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email, [recipient], msg.as_string())
                server.quit()
                logger.info("Successfully dispatched HR shortlist digest email via SMTP", recipient=recipient, shortlisted_count=shortlisted_count)
                return {
                    "status": "SENT",
                    "recipient": recipient,
                    "shortlisted_count": shortlisted_count,
                    "total_count": total_count,
                    "attachment": attached_filename,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to send email via SMTP. Falling back to local audit storage", error=str(e))

        audit_dir = Path("app/data/email_audit")
        audit_dir.mkdir(parents=True, exist_ok=True)
        file_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = audit_dir / f"hr_email_digest_{file_stamp}.html"

        try:
            with open(audit_file, "w", encoding="utf-8") as f:
                f.write(html_body)
            logger.info("Saved local audit copy of HR digest email", path=str(audit_file), recipient=recipient)
        except Exception as e:
            logger.warning("Could not write audit email file", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "message": "SMTP credentials not set. Saved full HTML email digest to local audit storage.",
            "recipient": recipient,
            "shortlisted_count": shortlisted_count,
            "total_count": total_count,
            "audit_file": str(audit_file),
            "attachment": attached_filename,
            "delivery_method": "LOCAL_AUDIT_FILE"
        }

    def _build_html_email_template(
        self,
        total_count: int,
        shortlisted_count: int,
        review_count: int,
        rejected_count: int,
        shortlisted_candidates: List[Dict[str, Any]],
        timestamp_str: str,
        rejected_candidates: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Generates executive styled HTML email content with official GWC DATA.AI branding & colors."""
        rows_html = ""
        if shortlisted_candidates:
            for idx, c in enumerate(shortlisted_candidates, start=1):
                name = c.get("candidate_name", "Applicant")
                email = c.get("email", "N/A")
                phone = c.get("phone") or "N/A"
                role = c.get("job_role", "N/A").replace("_", " ").title()
                reason = c.get("reasoning") or c.get("decision_reason") or "Met mandatory job qualifications."

                rows_html += f"""
                <tr style="border-bottom: 1px solid #f3e8ff;">
                    <td style="padding: 14px; font-weight: 600; color: #262626;">{idx}. {name}</td>
                    <td style="padding: 14px; color: #7030B1; font-weight: 600;">{role}</td>
                    <td style="padding: 14px; color: #525252; font-size: 13px;">{email}<br>{phone}</td>
                    <td style="padding: 14px; color: #166534; background-color: #f0fdf4; border-radius: 8px; font-size: 13px; line-height: 1.5;">
                        <strong>Selection Reasoning:</strong><br>{reason}
                    </td>
                </tr>
                """
        else:
            rows_html = """
            <tr>
                <td colspan="4" style="padding: 20px; text-align: center; color: #525252;">
                    No candidates met the shortlist threshold in this screening batch.
                </td>
            </tr>
            """

        # Check for employee referrals
        all_screened = (shortlisted_candidates or []) + (rejected_candidates or [])
        referred_candidates = [c for c in all_screened if c.get("is_referred") or c.get("referred_by_name")]

        referral_section_html = ""
        if referred_candidates:
            ref_rows = ""
            for r in referred_candidates:
                ref_name = r.get("candidate_name", "Applicant")
                ref_role = (r.get("job_role") or "").replace("_", " ").title()
                referrer = f"{r.get('referred_by_name')} ({r.get('referred_by_id', 'Employee')})"
                ref_status = r.get("status") or r.get("system_decision") or "UNKNOWN"
                ref_score = r.get("weighted_score") or r.get("weightage_score") or "N/A"

                is_rej = str(ref_status).upper() == "REJECTED"
                status_color = "#dc2626" if is_rej else "#16a34a"
                alert_tag = "⚠️ AI Rejected — HR Review Recommended" if is_rej else "✅ Qualified"

                ref_rows += f"""
                <tr style="border-bottom: 1px solid #f3e8ff;">
                    <td style="padding: 12px; font-weight: 600;">{ref_name}</td>
                    <td style="padding: 12px; color: #7030B1; font-weight: 600;">{ref_role}</td>
                    <td style="padding: 12px; color: #1e1b4b; font-weight: 600;">🌟 {referrer}</td>
                    <td style="padding: 12px; color: {status_color}; font-weight: 700;">{ref_score}/100 ({alert_tag})</td>
                </tr>
                """

            referral_section_html = f"""
            <div style="margin-top: 28px; background: #faf5ff; border: 1.5px solid #d8b4fe; border-radius: 14px; padding: 18px;">
                <h3 style="color: #7030B1; margin: 0 0 8px 0; font-size: 16px; font-weight: 800;">
                    🌟 Employee Referrals Summary ({len(referred_candidates)})
                </h3>
                <p style="font-size: 12.5px; color: #4c1d95; margin: 0 0 12px 0;">
                    Internal referrals detected in this screening drive. Any AI-rejected referral is flagged below for HR discretionary review:
                </p>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; background: #ffffff; border-radius: 8px; overflow: hidden;">
                    <thead>
                        <tr style="background: #7030B1; color: #ffffff;">
                            <th style="padding: 10px; text-align: left;">Candidate</th>
                            <th style="padding: 10px; text-align: left;">Role</th>
                            <th style="padding: 10px; text-align: left;">Referred By</th>
                            <th style="padding: 10px; text-align: left;">AI Score &amp; Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {ref_rows}
                    </tbody>
                </table>
            </div>
            """

        css_style = """
            body { font-family: 'Poppins', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #faf8fc; color: #262626; margin: 0; padding: 24px; }
            .container { max-width: 720px; background: #ffffff; margin: 0 auto; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 30px rgba(112, 48, 177, 0.12); border: 1px solid #e5e5e5; }
            .header { background: linear-gradient(135deg, #7030B1 0%, #B56DD3 60%, #FF6B00 100%); color: #ffffff; padding: 32px 28px; text-align: center; border-bottom: 4px solid #FF6B00; }
            .header h1 { margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.15); }
            .header p { margin: 8px 0 0 0; opacity: 0.95; font-size: 14px; font-weight: 500; letter-spacing: 0.3px; }
            .content { padding: 28px; }
            .metric-card { flex: 1; padding: 16px 12px; background: #faf5ff; border-radius: 12px; text-align: center; border: 1px solid #e9d5ff; }
            .metric-val { font-size: 24px; font-weight: 800; color: #7030B1; margin-top: 4px; }
            .metric-label { font-size: 11px; text-transform: uppercase; color: #7030B1; font-weight: 700; letter-spacing: 0.5px; }
            .purple-bg { background: #faf5ff !important; border-color: #ddd6fe !important; }
            .orange-bg { background: #fff7ed !important; border-color: #ffedd5 !important; }
            .orange-text { color: #FF6B00 !important; }
            .purple-text { color: #7030B1 !important; }
            .green { color: #166534 !important; }
            .yellow { color: #b45309 !important; }
            .red { color: #991b1b !important; }
            table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 18px; font-size: 14px; border-radius: 12px; overflow: hidden; border: 1px solid #f3e8ff; }
            th { background: linear-gradient(90deg, #7030B1 0%, #B56DD3 100%); color: #ffffff; text-align: left; padding: 14px; font-size: 12px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; }
            td { padding: 14px; border-bottom: 1px solid #f3e8ff; vertical-align: top; }
            .footer { background: linear-gradient(90deg, #faf5ff 0%, #fff7ed 100%); padding: 20px; text-align: center; font-size: 12px; color: #7030B1; font-weight: 600; border-top: 1px solid #e5e5e5; }
        """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{css_style}</style>
</head>
<body>
    <div class="container">
        <!-- GWC Data.Ai Brand Bar -->
        <div style="background: #ffffff; padding: 20px 28px; text-align: center; border-bottom: 2px solid #faf5ff;">
            <img src="https://gwcdata.ai/images/logo.svg" alt="GWC DATA.AI" style="height: 44px; width: auto;" />
        </div>
        
        <div class="header">
            <h1>🤖 Candidate Resume Screening Digest</h1>
            <p>Enterprise AI Recruitment & Executive Shortlist Notification</p>
        </div>
        
        <div class="content">
            <p style="font-size: 15px; line-height: 1.6; margin-top: 0; color: #525252;">
                Hello HR Recruitment Team,<br><br>
                The <strong>GWC DATA.AI Automated Screening Agent</strong> has completed evaluating incoming candidate form responses. Below is the executive metrics summary and detailed shortlist report.
            </p>

            <!-- Summary Metrics Cards -->
            <table style="width: 100%; margin-bottom: 24px; border: none;">
                <tr>
                    <td style="width: 25%; padding: 6px; border: none;">
                        <div class="metric-card purple-bg">
                            <div class="metric-label purple-text">Total Evaluated</div>
                            <div class="metric-val purple-text">{total_count}</div>
                        </div>
                    </td>
                    <td style="width: 25%; padding: 6px; border: none;">
                        <div class="metric-card orange-bg">
                            <div class="metric-label orange-text">Shortlisted</div>
                            <div class="metric-val orange-text">{shortlisted_count}</div>
                        </div>
                    </td>
                    <td style="width: 25%; padding: 6px; border: none;">
                        <div class="metric-card" style="background: #fffbeb; border-color: #fef3c7;">
                            <div class="metric-label yellow">HR Review</div>
                            <div class="metric-val yellow">{review_count}</div>
                        </div>
                    </td>
                    <td style="width: 25%; padding: 6px; border: none;">
                        <div class="metric-card" style="background: #fef2f2; border-color: #fecaca;">
                            <div class="metric-label red">Rejected</div>
                            <div class="metric-val red">{rejected_count}</div>
                        </div>
                    </td>
                </tr>
            </table>

            <h3 style="color: #7030B1; margin-bottom: 8px; font-size: 17px; font-weight: 700;">🌟 Shortlisted Candidates ({shortlisted_count})</h3>
            <p style="font-size: 13px; color: #7030B1; margin-top: 0;">
                Candidates who passed all mandatory criteria and exceeded shortlist thresholds:
            </p>

            <table>
                <thead>
                    <tr>
                        <th>Candidate Name</th>
                        <th>Job Role</th>
                        <th>Contact Info</th>
                        <th>AI Selection Reasoning</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>

            {referral_section_html}

            <div style="margin-top: 24px; padding: 16px; background: linear-gradient(135deg, #faf5ff 0%, #fff7ed 100%); border-radius: 12px; border: 1px solid #FF6B00; font-size: 13px; color: #c2410c;">
                📎 <strong>Attached Ledger:</strong> The full candidate screening database (<code>screening_results.csv</code>) is attached to this email containing all applicant details.
            </div>
        </div>

        <div class="footer">
            GWC DATA.AI Enterprise Automated Recruitment Platform • {timestamp_str}
        </div>
    </div>
</body>
</html>"""

    def send_teams_interview_invite(
        self,
        candidate_name: str,
        candidate_email: str,
        job_role: str,
        employee_name: str,
        employee_email: str,
        hr_email: str,
        display_date: str,
        display_time_range: str,
        teams_join_url: str,
        ics_bytes: bytes,
        ics_filename: str
    ) -> Dict[str, Any]:
        """
        Sends multi-party Microsoft Teams Meeting Invitation to Candidate, Interviewer/Employee, and HR.
        Attaches .ics iCalendar invite file.
        """
        recipients = list(set([candidate_email, employee_email, hr_email]))
        subject = f"📅 Interview Invitation: {candidate_name} - {job_role} ({display_date})"

        css_style = """
            body { font-family: 'Poppins', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #faf8fc; color: #262626; margin: 0; padding: 24px; }
            .card { max-width: 680px; background: #ffffff; margin: 0 auto; border-radius: 20px; overflow: hidden; box-shadow: 0 12px 30px rgba(255, 107, 0, 0.15); border: 1px solid #fed7aa; }
            .header { background: linear-gradient(135deg, #7030B1 0%, #B56DD3 50%, #FF6B00 100%); color: #ffffff; padding: 32px 24px; text-align: center; border-bottom: 4px solid #FF6B00; }
            .header h2 { margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.15); }
            .body { padding: 28px; line-height: 1.6; }
            .details-box { background: #faf5ff; padding: 20px; border-radius: 14px; margin: 20px 0; border-left: 5px solid #FF6B00; border-top: 1px solid #f3e8ff; border-right: 1px solid #f3e8ff; border-bottom: 1px solid #f3e8ff; }
            .details-title { font-size: 15px; font-weight: 700; color: #7030B1; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
            .join-btn { display: inline-block; background: linear-gradient(135deg, #7030B1 0%, #FF6B00 100%); color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 12px; font-weight: 800; font-size: 15px; margin-top: 12px; box-shadow: 0 4px 14px rgba(255, 107, 0, 0.35); transition: transform 0.2s; }
            .footer { background: linear-gradient(90deg, #faf5ff 0%, #fff7ed 100%); padding: 20px; text-align: center; font-size: 12px; color: #7030B1; font-weight: 600; border-top: 1px solid #fed7aa; }
        """

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{css_style}</style>
</head>
<body>
    <div class="card">
        <!-- GWC Data.Ai Brand Bar -->
        <div style="background: #ffffff; padding: 20px 28px; text-align: center; border-bottom: 2px solid #faf5ff;">
            <img src="https://gwcdata.ai/images/logo.svg" alt="GWC DATA.AI" style="height: 44px; width: auto;" />
        </div>

        <div class="header">
            <h2>📅 Microsoft Teams Technical Interview Invitation</h2>
        </div>
        <div class="body">
            <p style="font-size: 16px; margin-top: 0; color: #262626;">Dear <strong>{candidate_name}</strong>,</p>
            <p style="color: #525252;">You have been officially scheduled for a Technical Interview for the <strong>{job_role}</strong> position at <strong>GWC DATA.AI</strong>.</p>
            
            <div class="details-box">
                <div class="details-title">📌 Interview Session Details</div>
                <p style="margin: 0 0 8px 0; color: #262626;"><strong>📅 Date:</strong> {display_date}</p>
                <p style="margin: 0 0 8px 0; color: #262626;"><strong>⏰ Time Slot:</strong> {display_time_range}</p>
                <p style="margin: 0 0 8px 0; color: #262626;"><strong>👤 Interviewer:</strong> {employee_name} (<a href="mailto:{employee_email}" style="color: #7030B1;">{employee_email}</a>)</p>
                <p style="margin: 0 0 0 0; color: #262626;"><strong>💼 HR Recruiter Contact:</strong> <a href="mailto:{hr_email}" style="color: #FF6B00;">{hr_email}</a></p>
            </div>

            <p style="text-align: center; margin: 28px 0 20px 0;">
                <a href="{teams_join_url}" class="join-btn" target="_blank">👉 Join Microsoft Teams Meeting</a>
            </p>

            <div style="margin-top: 24px; padding: 16px; background: #fff7ed; border-radius: 12px; border: 1px solid #ffedd5; font-size: 13px; color: #c2410c;">
                📎 <strong>Calendar Invite Attached:</strong> Standard iCalendar invite (<code>{ics_filename}</code>) is attached to this email. Opening it will automatically block this time slot in your calendar.
            </div>
        </div>
        <div class="footer">
            GWC DATA.AI Enterprise Automated Recruitment Platform
        </div>
    </div>
</body>
</html>"""

        hr_sender = hr_email or settings.HR_NOTIFICATION_EMAIL or self.sender_email
        smtp_recipients = list(dict.fromkeys([candidate_email, employee_email, hr_sender]))

        msg = MIMEMultipart()
        msg["From"] = f"GWC DATA.AI HR Recruitment <{hr_sender}>"
        msg["To"] = candidate_email
        msg["Cc"] = employee_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        part = MIMEBase("text", "calendar", method="REQUEST", name=ics_filename)
        part.set_payload(ics_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={ics_filename}")
        msg.attach(part)

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email or hr_sender, smtp_recipients, msg.as_string())
                server.quit()
                logger.info(
                    "Successfully dispatched MS Teams interview email invite via SMTP",
                    to=candidate_email,
                    cc=employee_email,
                    from_hr=hr_sender,
                    teams_link=teams_join_url
                )
                return {
                    "status": "SENT",
                    "to": candidate_email,
                    "cc": employee_email,
                    "from": hr_sender,
                    "teams_url": teams_join_url,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to send MS Teams invite via SMTP. Falling back to local audit file", error=str(e))


        audit_dir = Path("app/data/email_audit")
        audit_dir.mkdir(parents=True, exist_ok=True)
        file_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = audit_dir / f"teams_invite_{candidate_name.replace(' ', '_')}_{file_stamp}.html"

        try:
            with open(audit_file, "w", encoding="utf-8") as f:
                f.write(html_body)
            logger.info("Saved local audit copy of Teams interview invite", path=str(audit_file))
        except Exception as e:
            logger.warning("Could not write Teams audit email file", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "message": "Saved MS Teams HTML interview invite to local audit storage.",
            "recipients": recipients,
            "teams_url": teams_join_url,
            "audit_file": str(audit_file),
            "delivery_method": "LOCAL_AUDIT_FILE"
        }

    def send_interviewer_availability_request(
        self,
        candidate_name: str,
        candidate_id: str,
        job_role: str,
        candidate_email: str,
        employee_name: str,
        employee_email: str,
        hr_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an official GWC DATA.AI availability request email to the assigned technical employee (interviewer).
        Asks the employee to reply to the email with their preferred availability timing window.
        """
        hr_contact = hr_email or settings.HR_NOTIFICATION_EMAIL or self.sender_email
        recipients = [employee_email]
        if hr_contact and hr_contact not in recipients:
            recipients.append(hr_contact)

        subject = f"🔔 [Action Required] Technical Interview Availability Request: {candidate_name} ({job_role})"

        css_style = """
        body { font-family: 'Poppins', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #FAF8FC; margin: 0; padding: 20px; color: #262626; }
        .email-container { max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(112, 48, 177, 0.08); border: 1px solid #FAF5FF; }
        .header { background: linear-gradient(135deg, #7030B1 0%, #B56DD3 60%, #FF6B00 100%); padding: 32px 30px; text-align: center; color: #ffffff; }
        .header img { height: 42px; margin-bottom: 12px; background: transparent; }
        .header h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
        .content { padding: 32px 30px; }
        .card { background: #FAF5FF; border-left: 4px solid #7030B1; padding: 18px 20px; border-radius: 8px; margin: 20px 0; }
        .instruction-card { background: #FFF7ED; border-left: 4px solid #FF6B00; padding: 18px 20px; border-radius: 8px; margin: 20px 0; color: #9A3412; }
        .footer { background: #FAF8FC; padding: 18px 30px; text-align: center; font-size: 12px; color: #737373; border-top: 1px solid #FAF5FF; }
        """

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Interview Availability Request</title>
    <style>{css_style}</style>
</head>
<body>
    <div class="email-container">
        <div class="header">
            <img src="https://gwcdata.ai/images/logo.svg" alt="GWC DATA.AI Logo">
            <h1>Technical Interview Availability Request</h1>
        </div>
        <div class="content">
            <p style="font-size: 15px; line-height: 1.5; color: #262626;">
                Hi <strong>{employee_name}</strong>,
            </p>
            <p style="font-size: 14px; line-height: 1.6; color: #525252;">
                You have been assigned by HR as the primary technical interviewer for candidate <strong>{candidate_name}</strong> who has been shortlisted for the <strong>{job_role}</strong> position.
            </p>

            <div class="card">
                <h3 style="margin: 0 0 10px 0; color: #7030B1; font-size: 15px;">Candidate Information</h3>
                <p style="margin: 0 0 6px 0; color: #262626; font-size: 13px;"><strong>Candidate Name:</strong> {candidate_name}</p>
                <p style="margin: 0 0 6px 0; color: #262626; font-size: 13px;"><strong>Candidate ID:</strong> {candidate_id}</p>
                <p style="margin: 0 0 6px 0; color: #262626; font-size: 13px;"><strong>Applied Position:</strong> {job_role}</p>
                <p style="margin: 0 0 0 0; color: #262626; font-size: 13px;"><strong>Email:</strong> {candidate_email}</p>
            </div>

            <div class="instruction-card">
                <h3 style="margin: 0 0 8px 0; color: #C2410C; font-size: 15px;">⚡ Action Required (Reply to this Email)</h3>
                <p style="margin: 0; font-size: 13px; line-height: 1.5;">
                    Please <strong>reply directly to this email thread</strong> with your preferred timing window for conducting this 45–60 minute technical interview (e.g. <em>"I am available tomorrow August 18th from 3:00 PM to 4:00 PM IST"</em>).
                </p>
            </div>

            <p style="font-size: 13px; color: #737373; line-height: 1.5;">
                Once you reply, our AI recruitment assistant will automatically generate the Microsoft Teams meeting link, block your calendar, and dispatch invitations to all attendees.
            </p>
        </div>
        <div class="footer">
            GWC DATA.AI Enterprise Automated Recruitment Platform • HR Recruiter: {hr_contact}
        </div>
    </div>
</body>
</html>"""

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = employee_email
        if hr_contact and hr_contact != employee_email:
            msg["Cc"] = hr_contact
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email, recipients, msg.as_string())
                server.quit()
                logger.info("Dispatched interviewer availability request email via SMTP", employee=employee_email, candidate=candidate_name)
                return {
                    "status": "SENT",
                    "recipient": employee_email,
                    "cc": hr_contact,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to send availability request email via SMTP. Falling back to local audit file", error=str(e))

        audit_dir = Path("app/data/email_audit")
        audit_dir.mkdir(parents=True, exist_ok=True)
        file_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audit_file = audit_dir / f"availability_request_{employee_name.replace(' ', '_')}_{file_stamp}.html"

        try:
            with open(audit_file, "w", encoding="utf-8") as f:
                f.write(html_body)
            logger.info("Saved local audit copy of availability request email", path=str(audit_file))
        except Exception as e:
            logger.warning("Could not write availability request audit email", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "message": "Saved availability request email to local audit storage.",
            "recipient": employee_email,
            "cc": hr_contact,
            "audit_file": str(audit_file),
            "delivery_method": "LOCAL_AUDIT_FILE"
        }

    def send_interviewer_copilot_briefing(
        self,
        employee_email: str,
        employee_name: str,
        candidate_record: Dict[str, Any],
        question_kit: Dict[str, Any],
        teams_meeting_url: Optional[str] = None,
        schedule_display: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends the AI Interviewer Copilot Question Kit Briefing directly to the assigned technical interviewer.
        """
        candidate_name = candidate_record.get("candidate_name", "Applicant")
        raw_role = candidate_record.get("job_role", "PYTHON_DEV")
        job_role = raw_role.replace("_", " ").title()
        score = candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "85"
        hr_contact = settings.HR_NOTIFICATION_EMAIL or self.sender_email

        subject = f"📋 [Interviewer Briefing] AI Question Kit for {candidate_name} ({job_role})"

        # Build Deep Dive HTML
        deep_dives_html = "".join([
            f"""<div style="background: #faf5ff; border-left: 4px solid #7030B1; padding: 14px 18px; border-radius: 8px; margin-bottom: 14px;">
                <p style="margin: 0 0 6px 0; font-weight: 700; color: #7030B1; font-size: 14px;">❓ Question:</p>
                <p style="margin: 0 0 10px 0; color: #1e1b4b; font-size: 13.5px; line-height: 1.5;">{q.get('question')}</p>
                <p style="margin: 0 0 4px 0; font-weight: 600; color: #166534; font-size: 12.5px;">🎯 What to look for:</p>
                <p style="margin: 0 0 8px 0; color: #374151; font-size: 12.5px;">{q.get('what_to_look_for')}</p>
                <p style="margin: 0 0 4px 0; font-weight: 600; color: #9a3412; font-size: 12.5px;">⚡ Follow-up:</p>
                <p style="margin: 0; color: #4b5563; font-size: 12.5px; font-style: italic;">{q.get('follow_up')}</p>
            </div>"""
            for q in question_kit.get("project_deep_dives", [])
        ])

        # Build Core Tech HTML
        core_tech_html = "".join([
            f"""<div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 14px 18px; border-radius: 8px; margin-bottom: 14px;">
                <p style="margin: 0 0 4px 0; font-weight: 700; color: #1d4ed8; font-size: 13px; text-transform: uppercase;">🔹 {q.get('topic')}</p>
                <p style="margin: 0 0 8px 0; color: #1e293b; font-size: 13.5px; font-weight: 600;">{q.get('question')}</p>
                <ul style="margin: 0; padding-left: 18px; color: #475569; font-size: 12.5px;">
                    {''.join([f'<li>{pt}</li>' for pt in q.get('ideal_answer_points', [])])}
                </ul>
            </div>"""
            for q in question_kit.get("core_technical_questions", [])
        ])

        # Build Red Flags HTML
        red_flags_html = "".join([
            f"""<li style="margin-bottom: 6px; color: #991b1b; font-size: 13px; line-height: 1.4;">⚠️ {rf}</li>"""
            for rf in question_kit.get("verification_red_flags", [])
        ])

        sys_design = question_kit.get("system_design_challenge", {})

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI Interviewer Copilot Briefing</title>
</head>
<body style="font-family: 'Poppins', 'Segoe UI', Arial, sans-serif; background-color: #faf8fc; margin: 0; padding: 20px; color: #262626;">
    <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(112, 48, 177, 0.08); border: 1px solid #FAF5FF;">
        
        <div style="background: linear-gradient(135deg, #7030B1 0%, #B56DD3 60%, #FF6B00 100%); padding: 28px 24px; text-align: center; color: #ffffff;">
            <img src="https://gwcdata.ai/images/logo.svg" alt="GWC DATA.AI Logo" style="height: 38px; margin-bottom: 10px;">
            <h1 style="margin: 0; font-size: 20px; font-weight: 700;">🤖 AI Interviewer Copilot Briefing</h1>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Tailored Candidate Resume Analysis & Question Kit</p>
        </div>

        <div style="padding: 26px 28px;">
            <p style="font-size: 15px; margin-top: 0;">Hi <strong>{employee_name}</strong>,</p>
            <p style="font-size: 13.5px; color: #525252; line-height: 1.5;">
                Below is your automated <strong>Technical Interview Kit</strong> for evaluating <strong>{candidate_name}</strong> ({job_role}). This kit was generated by analyzing the candidate's resume claims and screening rubric.
            </p>

            <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 10px; padding: 14px 18px; margin-bottom: 22px;">
                <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>👤 Candidate:</strong> {candidate_name} &bull; <strong>Role:</strong> {job_role}</p>
                <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>🏆 Screening Score:</strong> <span style="color: #7030B1; font-weight: 700;">{score}/100</span></p>
                {f'<p style="margin: 0 0 6px 0; font-size: 13px;"><strong>📅 Scheduled Slot:</strong> {schedule_display}</p>' if schedule_display else ''}
                {f'<p style="margin: 0; font-size: 13px;"><strong>🔗 Teams Meeting:</strong> <a href="{teams_meeting_url}" style="color: #7030B1; font-weight: 600;">Join Session</a></p>' if teams_meeting_url else ''}
            </div>

            <h3 style="color: #7030B1; font-size: 15px; border-bottom: 2px solid #FAF5FF; padding-bottom: 6px; margin-top: 24px;">🎯 1. Resume Project Deep-Dives</h3>
            {deep_dives_html}

            <h3 style="color: #1d4ed8; font-size: 15px; border-bottom: 2px solid #FAF5FF; padding-bottom: 6px; margin-top: 24px;">💻 2. Core Framework & Technical Probing</h3>
            {core_tech_html}

            <h3 style="color: #7030B1; font-size: 15px; border-bottom: 2px solid #FAF5FF; padding-bottom: 6px; margin-top: 24px;">🏗️ 3. Domain System Design Challenge</h3>
            <div style="background: #fff7ed; border-left: 4px solid #ea580c; padding: 14px 18px; border-radius: 8px; margin-bottom: 14px;">
                <p style="margin: 0 0 8px 0; font-weight: 600; color: #9a3412; font-size: 13.5px;">{sys_design.get('scenario')}</p>
                <p style="margin: 0 0 4px 0; font-weight: 700; color: #c2410c; font-size: 12px; text-transform: uppercase;">Evaluation Criteria:</p>
                <ul style="margin: 0; padding-left: 18px; color: #431407; font-size: 12.5px;">
                    {''.join([f'<li>{c}</li>' for c in sys_design.get('key_criteria', [])])}
                </ul>
            </div>

            <h3 style="color: #b91c1c; font-size: 15px; border-bottom: 2px solid #FAF5FF; padding-bottom: 6px; margin-top: 24px;">🚨 4. Verification Checkpoints & Red Flags</h3>
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px;">
                <ul style="margin: 0; padding-left: 18px;">
                    {red_flags_html}
                </ul>
            </div>
        </div>

        <div style="background: #FAF8FC; padding: 16px 28px; text-align: center; font-size: 12px; color: #737373; border-top: 1px solid #FAF5FF;">
            GWC DATA.AI Enterprise Automated Recruitment Platform • Internal Interviewer Briefing
        </div>
    </div>
</body>
</html>"""

        recipients = [employee_email]
        if hr_contact and hr_contact != employee_email:
            recipients.append(hr_contact)

        msg = MIMEMultipart()
        msg["From"] = f"GWC DATA.AI Interviewer Copilot <{hr_contact}>"
        msg["To"] = employee_email
        if hr_contact and hr_contact != employee_email:
            msg["Cc"] = hr_contact
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email or hr_contact, recipients, msg.as_string())
                server.quit()
                logger.info("Dispatched Interviewer Copilot Briefing via SMTP", to=employee_email, candidate=candidate_name)
                return {"status": "SENT", "recipient": employee_email, "delivery_method": "SMTP"}
            except Exception as e:
                logger.error("Failed to send copilot briefing via SMTP", error=str(e))

        return {"status": "AUDITED_LOCAL", "recipient": employee_email, "delivery_method": "LOCAL_AUDIT"}

    def send_interview_questions_docx(
        self,
        employee_email: str,
        employee_name: str,
        candidate_record: Dict[str, Any],
        docx_bytes: bytes,
        docx_filename: str,
        resume_bytes: Optional[bytes] = None,
        resume_filename: Optional[str] = None,
        teams_meeting_url: Optional[str] = None,
        schedule_display: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an official email to the assigned interviewer with:
        1. GWC-branded Technical Interview Questions Word Document (.docx) containing 10 tailored questions.
        2. Candidate's Official Resume File (.pdf/.docx).
        """
        candidate_name = candidate_record.get("candidate_name", "Applicant")
        raw_role = candidate_record.get("job_role", "PYTHON_DEV")
        job_role = raw_role.replace("_", " ").title()
        score = candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "88.5"
        hr_contact = settings.HR_NOTIFICATION_EMAIL or self.sender_email

        subject = f"📎 [Interview Question Sheet & Resume] Technical Evaluation Kit for {candidate_name} ({job_role})"

        resume_callout = f"<li><strong>📄 Candidate Resume ({resume_filename or 'Resume.pdf'})</strong>: Complete original resume submitted by candidate.</li>" if resume_bytes else ""

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: 'Poppins', 'Segoe UI', Arial, sans-serif; background-color: #faf8fc; margin: 0; padding: 20px; color: #262626;">
    <div style="max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(112, 48, 177, 0.08); border: 1px solid #FAF5FF;">
        
        <div style="background: linear-gradient(135deg, #7030B1 0%, #B56DD3 60%, #FF6B00 100%); padding: 28px 24px; text-align: center; color: #ffffff;">
            <img src="https://gwcdata.ai/images/logo.svg" alt="GWC DATA.AI Logo" style="height: 38px; margin-bottom: 8px;">
            <h1 style="margin: 0; font-size: 20px; font-weight: 700;">GWC DATA.AI Technical Evaluation Kit</h1>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Tailored Interview Questions (.docx) & Candidate Resume Attached</p>
        </div>

        <div style="padding: 26px 28px;">
            <p style="font-size: 15px; margin-top: 0;">Hi <strong>{employee_name}</strong>,</p>
            <p style="font-size: 13.5px; color: #525252; line-height: 1.6;">
                Attached to this email are the official <strong>Technical Interview Question Sheet</strong> (<code>{docx_filename}</code>) and the candidate's <strong>Resume File</strong> for evaluating <strong>{candidate_name}</strong> for the <strong>{job_role}</strong> position.
            </p>

            <!-- Candidate Metadata Box -->
            <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 10px; padding: 14px 18px; margin: 18px 0;">
                <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>👤 Candidate Name:</strong> {candidate_name}</p>
                <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>💼 Target Position:</strong> {job_role}</p>
                <p style="margin: 0 0 6px 0; font-size: 13px;"><strong>🏆 Screening Score:</strong> <span style="color: #7030B1; font-weight: 700;">{score}/100</span></p>
                {f'<p style="margin: 0 0 6px 0; font-size: 13px;"><strong>📅 Scheduled Slot:</strong> {schedule_display}</p>' if schedule_display else ''}
                {f'<p style="margin: 0; font-size: 13px;"><strong>🔗 Teams Meeting:</strong> <a href="{teams_meeting_url}" style="color: #7030B1; font-weight: 700;">Join MS Teams Call</a></p>' if teams_meeting_url else ''}
            </div>

            <!-- Attachments Callout -->
            <div style="background: #FFF7ED; border-left: 4px solid #FF6B00; border-radius: 8px; padding: 14px 18px; margin: 20px 0;">
                <p style="margin: 0 0 6px 0; font-weight: 700; color: #C2410C; font-size: 13.5px;">📎 Email Attachments Included (2 Files):</p>
                <ul style="margin: 0; padding-left: 18px; color: #9A3412; font-size: 12.5px; line-height: 1.6;">
                    <li><strong>📋 10 Tailored Technical Questions (<code>{docx_filename}</code>)</strong>: Resume-based questions, evaluation checkboxes, and scoring rubric.</li>
                    {resume_callout}
                </ul>
            </div>

            <p style="font-size: 13px; color: #737373; line-height: 1.5;">
                You can review the attached resume and reference the Word document during the interview session to grade responses.
            </p>
        </div>

        <div style="background: #FAF8FC; padding: 16px 28px; text-align: center; font-size: 12px; color: #737373; border-top: 1px solid #FAF5FF;">
            GWC DATA.AI Enterprise Automated Recruitment Platform • HR Recruiter: {hr_contact}
        </div>
    </div>
</body>
</html>"""

        recipients = [employee_email]
        if hr_contact and hr_contact != employee_email:
            recipients.append(hr_contact)

        msg = MIMEMultipart()
        msg["From"] = f"GWC DATA.AI Technical Recruitment <{hr_contact}>"
        msg["To"] = employee_email
        if hr_contact and hr_contact != employee_email:
            msg["Cc"] = hr_contact
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        # 1. Attach DOCX Question Sheet
        part_docx = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
        part_docx.set_payload(docx_bytes)
        encoders.encode_base64(part_docx)
        part_docx.add_header("Content-Disposition", f"attachment; filename={docx_filename}")
        msg.attach(part_docx)

        # 2. Attach Candidate Resume File
        if resume_bytes:
            r_fname = resume_filename or f"Resume_{candidate_name.replace(' ', '_')}.pdf"
            r_mime = "application/pdf" if r_fname.lower().endswith(".pdf") else "application/octet-stream"
            main_type, sub_type = r_mime.split("/")
            part_resume = MIMEBase(main_type, sub_type)
            part_resume.set_payload(resume_bytes)
            encoders.encode_base64(part_resume)
            part_resume.add_header("Content-Disposition", f"attachment; filename={r_fname}")
            msg.attach(part_resume)

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email or hr_contact, recipients, msg.as_string())
                server.quit()
                logger.info("Successfully emailed DOCX Question Sheet and Candidate Resume via SMTP", to=employee_email, candidate=candidate_name, docx=docx_filename, resume=resume_filename)
                return {
                    "status": "SENT",
                    "recipient": employee_email,
                    "docx_filename": docx_filename,
                    "resume_filename": resume_filename,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to email DOCX question sheet and resume via SMTP", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "recipient": employee_email,
            "docx_filename": docx_filename,
            "resume_filename": resume_filename,
            "delivery_method": "LOCAL_AUDIT"
        }

    def send_hr_candidate_approval_notification(
        self,
        candidate: Dict[str, Any],
        recipient_email: Optional[str] = None,
        csv_attachment_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dispatches official HR Notification Email ONLY AFTER a candidate has been reviewed and approved in Human-in-the-Loop review.
        """
        recipient = recipient_email or settings.HR_NOTIFICATION_EMAIL
        cand_name = candidate.get("candidate_name", "Applicant")
        cand_id = candidate.get("candidate_id", "CAN-000")
        raw_role = candidate.get("job_role", "AI_ENGINEER")
        job_role = raw_role.replace("_", " ").title()
        score = candidate.get("weightage_score") or candidate.get("weighted_score") or "85"
        reasoning = candidate.get("reasoning") or candidate.get("decision_reason") or "Qualified candidate."
        hr_feedback = candidate.get("hr_feedback", "")
        email_addr = candidate.get("email", "N/A")
        phone_num = candidate.get("phone", "N/A")
        timestamp_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")

        subject = f"✅ [HR Approved] Candidate Shortlisted: {cand_name} ({job_role}) - Score: {score}/100"

        feedback_html = ""
        if hr_feedback:
            feedback_html = f"""
            <div style="margin-top: 14px; background: #FAF5FF; border: 1.5px solid #D8B4FE; border-radius: 8px; padding: 12px 16px;">
                <div style="font-size: 11px; font-weight: 700; color: #7030B1; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">💬 Applied HR Guidance &amp; Re-Evaluation Notes</div>
                <div style="font-size: 13px; color: #4C1D95; line-height: 1.4;">"{hr_feedback}"</div>
            </div>"""

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b;">
    <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #7030B1 0%, #B56DD3 50%, #FF6B00 100%); padding: 28px 32px; color: #ffffff;">
            <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; margin-bottom: 4px;">GWC DATA.AI • Human-in-the-Loop Recruitment</div>
            <h1 style="margin: 0; font-size: 22px; font-weight: 700; line-height: 1.3;">Candidate Approved for Interview</h1>
            <div style="font-size: 13px; opacity: 0.95; margin-top: 6px;">Reviewed and Approved by HR Recruiter on {timestamp_str}</div>
        </div>

        <!-- Content -->
        <div style="padding: 28px 32px;">
            <!-- Candidate Card -->
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px 20px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <div>
                        <h2 style="margin: 0; font-size: 18px; color: #0f172a;">{cand_name}</h2>
                        <div style="font-size: 13px; color: #7030B1; font-weight: 600; margin-top: 2px;">{job_role} • <span style="color: #64748b;">ID: {cand_id}</span></div>
                    </div>
                    <div style="background: #F0FDF4; border: 1px solid #86EFAC; color: #15803D; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700;">
                        Score: {score}/100
                    </div>
                </div>

                <div style="font-size: 13px; color: #475569; line-height: 1.6;">
                    <div>📧 <strong>Email:</strong> {email_addr}</div>
                    <div>📱 <strong>Phone:</strong> {phone_num}</div>
                    <div>🛡️ <strong>Review State:</strong> <span style="color: #15803D; font-weight: 700;">✅ HR Approved</span></div>
                </div>
            </div>

            <!-- AI Screening Reasoning -->
            <div style="margin-bottom: 20px;">
                <h3 style="font-size: 14px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0;">🤖 AI Screening &amp; Selection Assessment</h3>
                <div style="background: #FAF8FC; border-left: 4px solid #7030B1; padding: 14px 18px; border-radius: 0 8px 8px 0; font-size: 13.5px; line-height: 1.5; color: #334155;">
                    {reasoning}
                </div>
                {feedback_html}
            </div>

            <!-- Next Steps -->
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px;">
                <div style="font-size: 13px; font-weight: 700; color: #1D4ED8; margin-bottom: 4px;">🚀 Next Workflow Action:</div>
                <div style="font-size: 13px; color: #1E40AF; line-height: 1.4;">
                    Please open the <strong>HR Command Center</strong> to assign a Technical Interviewer. The system will automatically recommend interviewers based on skill alignment and capacity.
                </div>
            </div>

            <div style="text-align: center;">
                <a href="http://127.0.0.1:8000/" style="display: inline-block; background: linear-gradient(135deg, #7030B1 0%, #FF6B00 100%); color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-size: 14px; font-weight: 700;">
                    Open HR Command Center &rarr;
                </a>
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f8fafc; padding: 16px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
            GWC DATA.AI Enterprise Automated Recruitment Platform • Human-in-the-Loop Gated Pipeline
        </div>
    </div>
</body>
</html>"""

        msg = MIMEMultipart()
        msg["From"] = f"GWC DATA.AI Recruitment <{self.sender_email}>"
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        attached_filename = None
        if csv_attachment_path:
            csv_file = Path(csv_attachment_path)
            if csv_file.exists():
                try:
                    with open(csv_file, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    attached_filename = csv_file.name
                    part.add_header("Content-Disposition", f"attachment; filename={attached_filename}")
                    msg.attach(part)
                except Exception as e:
                    logger.warning("Could not attach CSV file to HR approval email", error=str(e))

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email, [recipient], msg.as_string())
                server.quit()
                logger.info("Successfully dispatched HR approval email via SMTP", recipient=recipient, candidate=cand_name)
                return {
                    "status": "SENT",
                    "recipient": recipient,
                    "candidate_name": cand_name,
                    "attachment": attached_filename,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to send HR approval email via SMTP", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "recipient": recipient,
            "candidate_name": cand_name,
            "attachment": attached_filename,
            "delivery_method": "LOCAL_AUDIT"
        }

    def send_bulk_hr_approval_digest(
        self,
        approved_candidates: List[Dict[str, Any]],
        recipient_email: Optional[str] = None,
        csv_attachment_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends a single consolidated executive digest email to HR when multiple candidates are approved in bulk.
        """
        recipient = recipient_email or settings.HR_NOTIFICATION_EMAIL
        count = len(approved_candidates)
        timestamp_str = datetime.now().strftime("%B %d, %Y - %H:%M UTC")

        subject = f"✅ [Bulk HR Approved] {count} Candidate(s) Approved for Technical Interview Pipeline"

        # Generate candidate rows HTML table
        rows_html = ""
        for idx, c in enumerate(approved_candidates[:50], start=1): # Top 50 in email body
            name = c.get("candidate_name", "Applicant")
            role = (c.get("job_role", "AI_ENGINEER")).replace("_", " ").title()
            score = c.get("weightage_score") or c.get("weighted_score") or "80"
            cid = c.get("candidate_id", "—")
            rows_html += f"""
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px 12px; font-weight: 600; color: #0f172a;">{idx}. {name} <span style="font-size: 11px; color: #64748b;">({cid})</span></td>
                <td style="padding: 10px 12px; color: #7030B1; font-weight: 600;">{role}</td>
                <td style="padding: 10px 12px; text-align: center;"><span style="background: #F0FDF4; color: #15803D; padding: 3px 8px; border-radius: 12px; font-weight: 700; font-size: 12px;">{score}/100</span></td>
            </tr>"""

        overflow_note = ""
        if count > 50:
            overflow_note = f"""<div style="font-size: 12px; color: #64748b; padding: 10px 12px; text-align: center;">... and {count - 50} more approved candidate(s) listed in the attached spreadsheet.</div>"""

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b;">
    <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #7030B1 0%, #B56DD3 50%, #FF6B00 100%); padding: 28px 32px; color: #ffffff;">
            <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; margin-bottom: 4px;">GWC DATA.AI • Bulk Human-in-the-Loop Approval</div>
            <h1 style="margin: 0; font-size: 22px; font-weight: 700; line-height: 1.3;">{count} Candidate(s) Approved in Bulk</h1>
            <div style="font-size: 13px; opacity: 0.95; margin-top: 6px;">Consolidated Batch Approval • {timestamp_str}</div>
        </div>

        <!-- Body -->
        <div style="padding: 28px 32px;">
            <div style="background: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 12px; padding: 16px 20px; margin-bottom: 22px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-size: 13px; font-weight: 700; color: #15803D;">✅ Batch Shortlist Approved</div>
                    <div style="font-size: 12.5px; color: #166534; margin-top: 2px;">{count} candidate(s) have been approved and unlocked for technical interview assignment.</div>
                </div>
                <div style="font-size: 24px; font-weight: 800; color: #15803D;">{count}</div>
            </div>

            <h3 style="font-size: 14px; font-weight: 700; color: #0f172a; margin: 0 0 10px 0;">📋 Approved Candidates Summary:</h3>
            <div style="border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; margin-bottom: 20px;">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                    <thead>
                        <tr style="background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                            <th style="padding: 10px 12px; color: #64748b; font-weight: 600;">Candidate</th>
                            <th style="padding: 10px 12px; color: #64748b; font-weight: 600;">Job Role</th>
                            <th style="padding: 10px 12px; color: #64748b; font-weight: 600; text-align: center;">Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
                {overflow_note}
            </div>

            <!-- Next Steps -->
            <div style="background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px;">
                <div style="font-size: 13px; font-weight: 700; color: #1D4ED8; margin-bottom: 4px;">🚀 Next Step: Assign Technical Interviewers</div>
                <div style="font-size: 13px; color: #1E40AF; line-height: 1.4;">
                    Open the <strong>HR Command Center</strong> to assign interviewers. AI recommendations are ready for each candidate based on skill alignment and current interviewer capacity.
                </div>
            </div>

            <div style="text-align: center;">
                <a href="http://127.0.0.1:8000/" style="display: inline-block; background: linear-gradient(135deg, #7030B1 0%, #FF6B00 100%); color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-size: 14px; font-weight: 700;">
                    Open HR Command Center &rarr;
                </a>
            </div>
        </div>

        <!-- Footer -->
        <div style="background: #f8fafc; padding: 16px 32px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
            GWC DATA.AI Enterprise Automated Recruitment Platform • Human-in-the-Loop Batch Pipeline
        </div>
    </div>
</body>
</html>"""

        msg = MIMEMultipart()
        msg["From"] = f"GWC DATA.AI Recruitment <{self.sender_email}>"
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        attached_filename = None
        if csv_attachment_path:
            csv_file = Path(csv_attachment_path)
            if csv_file.exists():
                try:
                    with open(csv_file, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    attached_filename = csv_file.name
                    part.add_header("Content-Disposition", f"attachment; filename={attached_filename}")
                    msg.attach(part)
                except Exception as e:
                    logger.warning("Could not attach CSV file to Bulk HR approval email", error=str(e))

        if self.username and self.password and self.smtp_server:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.sender_email, [recipient], msg.as_string())
                server.quit()
                logger.info("Successfully dispatched Bulk HR approval digest email via SMTP", recipient=recipient, count=count)
                return {
                    "status": "SENT",
                    "recipient": recipient,
                    "count": count,
                    "attachment": attached_filename,
                    "delivery_method": "SMTP"
                }
            except Exception as e:
                logger.error("Failed to send Bulk HR approval email via SMTP", error=str(e))

        return {
            "status": "AUDITED_LOCAL",
            "recipient": recipient,
            "count": count,
            "attachment": attached_filename,
            "delivery_method": "LOCAL_AUDIT"
        }



