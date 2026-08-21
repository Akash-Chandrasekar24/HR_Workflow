import structlog
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Response, status
from pydantic import BaseModel, Field

from app.services.referral_service import referral_service
from app.services.csv_storage import CSVStorageService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/referrals", tags=["Employee Referrals"])
storage_service = CSVStorageService()


class ReferralCreateRequest(BaseModel):
    candidate_name: str = Field(..., description="Full Name of the referred candidate")
    candidate_email: str = Field(..., description="Email address of the candidate")
    candidate_phone: Optional[str] = Field("", description="Phone number of the candidate")
    referred_by_name: str = Field(..., description="Name of the referring employee")
    referred_by_id: str = Field(..., description="Employee ID of the referrer (e.g. EMP-101)")
    referred_by_email: Optional[str] = Field("akashchandrasekar24@gmail.com", description="Email of the referring employee")
    department: Optional[str] = Field("Engineering", description="Department of referring employee")
    notes: Optional[str] = Field("Internal employee referral", description="Referral notes or relationship")


@router.get("", summary="Get Active Employee Referrals Registry")
async def get_all_referrals_endpoint():
    """
    Returns list of all active employee referrals and calculates live candidate match counts.
    """
    try:
        referrals = referral_service.get_all_referrals()
        candidates = storage_service.get_all_records()

        # Check which referrals have matching candidate submissions
        enriched_referrals = []
        for ref in referrals:
            ref_copy = dict(ref)
            matched_candidate = None
            for c in candidates:
                cand_email = (c.get("email") or "").strip().lower()
                if cand_email and cand_email == (ref.get("candidate_email") or "").strip().lower():
                    matched_candidate = {
                        "candidate_id": c.get("candidate_id"),
                        "candidate_name": c.get("candidate_name"),
                        "job_role": c.get("job_role"),
                        "status": c.get("status") or c.get("system_decision"),
                        "weighted_score": c.get("weighted_score") or c.get("weightage_score"),
                        "hr_approval_status": c.get("hr_approval_status"),
                        "referral_alert": c.get("referral_alert"),
                        "referral_alert_message": c.get("referral_alert_message")
                    }
                    break

            ref_copy["matched_application"] = matched_candidate
            enriched_referrals.append(ref_copy)

        return {
            "status": "SUCCESS",
            "count": len(enriched_referrals),
            "referrals": enriched_referrals
        }
    except Exception as e:
        logger.error("Failed to retrieve employee referrals", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve referrals: {str(e)}")


@router.post("/upload-roster", summary="Upload Excel Sheet of Employee Referrals")
async def upload_employee_referrals(file: UploadFile = File(...)):
    """
    Uploads an Excel (.xlsx/.xls) or CSV file containing employee referrals:
    Candidate Name, Candidate Email, Candidate Phone, Referred By (Employee Name),
    Employee ID, Employee Email, Department, Notes / Relationship.
    Automatically cross-references screened candidates and flags AI rejections.
    """
    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Only Excel (.xlsx/.xls) or CSV files are supported.")

    try:
        file_bytes = await file.read()
        imported = referral_service.import_referrals_from_excel_bytes(file_bytes, filename=file.filename)
        candidates = storage_service.get_all_records()

        matched_count = sum(1 for c in candidates if c.get("is_referred"))
        rejected_referred_count = sum(1 for c in candidates if c.get("referral_alert") == "REFERRED_REJECTED")

        return {
            "status": "SUCCESS",
            "message": f"Successfully uploaded {len(imported)} employee referrals from '{file.filename}'.",
            "count": len(imported),
            "matched_candidates_count": matched_count,
            "rejected_referred_alerts": rejected_referred_count,
            "referrals": imported
        }
    except Exception as e:
        logger.error("Failed to process employee referral upload", error=str(e))
        raise HTTPException(status_code=400, detail=f"Referral upload failed: {str(e)}")


@router.get("/template/excel", summary="Download Sample Excel Template for Employee Referrals")
async def download_referral_template_excel():
    """
    Generates and downloads a GWC DATA.AI styled Excel template with sample employee referral rows.
    """
    try:
        excel_bytes = referral_service.generate_sample_referral_template_excel()
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=GWC_Employee_Referral_Template.xlsx"}
        )
    except Exception as e:
        logger.error("Failed to generate referral Excel template", error=str(e))
        raise HTTPException(status_code=500, detail=f"Template generation failed: {str(e)}")


@router.delete("", summary="Clear Employee Referrals Registry")
async def clear_all_referrals():
    """Clears the employee referral registry."""
    referral_service.clear_referrals()
    return {"status": "SUCCESS", "message": "Cleared all employee referrals."}
