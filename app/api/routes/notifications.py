import structlog
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from app.services.csv_storage import CSVStorageService
from app.services.email_service import EmailService
from app.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Email Notifications"])
csv_storage = CSVStorageService()
email_service = EmailService()


class EmailDigestRequest(BaseModel):
    recipient_email: Optional[str] = Field(
        None,
        json_schema_extra={"example": "hr-recruiter@company.com"},
        description="Target HR email address. Defaults to configured HR_NOTIFICATION_EMAIL if omitted."
    )


@router.post(
    "/email-digest",
    summary="Send HR Shortlisted Candidates Email Digest with CSV Ledger Attachment"
)
async def send_hr_email_digest(payload: Optional[EmailDigestRequest] = None):
    """
    Fetches all screened candidate records from the ledger, filters shortlisted candidates,
    builds an executive HTML digest email with explicit AI selection reasoning statements,
    attaches the screening_results.csv file, and dispatches to HR.
    """
    target_email = payload.recipient_email if payload and payload.recipient_email else settings.HR_NOTIFICATION_EMAIL

    try:
        candidates = csv_storage.get_all_records()
        if not candidates:
            raise HTTPException(status_code=404, detail="No candidate screening records found in ledger to report.")

        csv_file_path = str(settings.csv_absolute_path)

        res = email_service.send_shortlist_digest(
            recipient_email=target_email,
            candidates=candidates,
            csv_attachment_path=csv_file_path
        )

        return {
            "status": "SUCCESS",
            "message": f"Successfully generated shortlist digest for HR ({target_email})",
            "details": res
        }

    except Exception as e:
        logger.error("Failed to send HR email digest", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Email dispatch failed: {str(e)}"
        )
