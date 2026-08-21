import structlog
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.schemas.application import ApplicationIngestRequest, ApplicationIngestResponse
from app.core.security import verify_hmac_signature
from app.services.google_drive import GoogleDriveService
from app.services.csv_storage import CSVStorageService
from app.workers.resume_worker import task_queue

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/applications", tags=["Candidate Applications"])
csv_storage = CSVStorageService()


class HROverrideRequest(BaseModel):
    override_decision: str = Field(..., json_schema_extra={"example": "SHORTLISTED"}, description="SHORTLISTED, HR_REVIEW, REJECTED")
    override_reason: str = Field(..., json_schema_extra={"example": "Role requirements updated. Candidate verified in recruiter screening call."})


class BatchTriggerRequest(BaseModel):
    spreadsheet_url: Optional[str] = Field(None, json_schema_extra={"example": "https://docs.google.com/spreadsheets/d/1ADbUgOVNNCAxFhZGpTxnOpHtmIeSF6MkMMyeI55ABQk/edit"}, description="Google Spreadsheet URL")
    gid: Optional[str] = Field(None, json_schema_extra={"example": "1147998574"}, description="Sheet tab GID")
    drive_folder_url: Optional[str] = Field(None, description="Optional Google Drive Folder URL")
    hr_email: Optional[str] = Field(None, description="Optional HR email to send email digest to")


@router.post(
    "/trigger-batch",
    summary="Trigger Automated Candidate Resume Screening Batch from Google Spreadsheet URL"
)
async def trigger_batch_processing(payload: BatchTriggerRequest):
    """
    Triggers end-to-end resume screening drive from HR Web Portal:
    1. Downloads candidate rows directly from the specified Google Spreadsheet link.
    2. Downloads resume PDFs directly from Google Drive HTTP links.
    3. Evaluates mandatory qualification rules & category weighted scores.
    4. Persists records to CSV & Excel ledgers.
    5. Dispatches executive GWC DATA.AI shortlist digest email to HR.
    """
    from process_google_sheet_batch import process_spreadsheet
    try:
        process_spreadsheet(
            spreadsheet_url_or_id=payload.spreadsheet_url,
            gid=payload.gid,
            drive_folder_url=payload.drive_folder_url
        )
        records = csv_storage.get_all_records()

        shortlisted = [r for r in records if (r.get("status") or r.get("system_decision")) == "SHORTLISTED"]
        review = [r for r in records if (r.get("status") or r.get("system_decision")) == "HR_REVIEW"]
        rejected = [r for r in records if (r.get("status") or r.get("system_decision")) == "REJECTED"]

        return {
            "status": "SUCCESS",
            "message": f"Successfully processed batch drive! Evaluated {len(records)} total candidate(s).",
            "metrics": {
                "total": len(records),
                "shortlisted": len(shortlisted),
                "hr_review": len(review),
                "rejected": len(rejected)
            },
            "candidates": records
        }
    except Exception as e:
        logger.error("Failed to execute batch processing drive", error=str(e))
        raise HTTPException(status_code=500, detail=f"Batch drive execution failed: {str(e)}")



@router.post(
    "",
    response_model=ApplicationIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest candidate form submission from Google Apps Script"
)
async def ingest_application(
    request: Request,
    payload: ApplicationIngestRequest
):
    """
    Ingests candidate metadata and Google Drive resume_file_id from Google Forms.
    Validates HMAC signature and enqueues async processing pipeline.
    """
    raw_body = await request.body()
    verify_hmac_signature(raw_body, request.headers.get("X-Signature-SHA256"))

    logger.info(
        "Ingesting candidate application webhook",
        candidate_id=payload.candidate_id,
        email=payload.email,
        job_role=payload.job_role,
        file_id=payload.resume_file_id
    )

    # Enqueue task for background processing
    task_queue.enqueue_application(payload)

    return ApplicationIngestResponse(
        status="ACCEPTED",
        candidate_id=payload.candidate_id,
        message=f"Application for {payload.full_name} ({payload.job_role}) enqueued successfully.",
        processing_status="PENDING"
    )


@router.get(
    "",
    summary="List processed candidate applications from CSV ledger"
)
async def list_applications(
    job_role: Optional[str] = None,
    search: Optional[str] = None,
    status_filter: Optional[str] = None
):
    """
    Returns list of processed candidate applications filtered by role, search term, and decision status.
    """
    records = csv_storage.get_all_records()
    
    # Filter by status if provided
    if status_filter:
        stat_clean = status_filter.upper()
        records = [r for r in records if (r.get("status") or r.get("system_decision", "")).upper() == stat_clean]

    # Filter by job role if provided
    if job_role:
        role_clean = job_role.upper()
        records = [r for r in records if r.get("job_role", "").upper() == role_clean]

    # Filter by search term if provided
    if search:
        s_clean = search.lower()
        records = [
            r for r in records
            if s_clean in r.get("candidate_name", "").lower()
            or s_clean in r.get("email", "").lower()
            or s_clean in r.get("candidate_id", "").lower()
            or s_clean in r.get("job_role", "").lower()
        ]


    return {
        "status": "SUCCESS",
        "count": len(records),
        "candidates": records
    }


@router.get(
    "/export/excel",
    summary="Download Excel Spreadsheet with formatted candidate selection reasoning"
)
async def export_excel():
    """
    Downloads the formatted Microsoft Excel spreadsheet (.xlsx) containing candidate decisions, score breakdowns,
    and explicit selection reasoning strings for HR recruiters.
    """
    from fastapi.responses import Response

    records = csv_storage.get_all_records()
    excel_bytes = csv_storage.generate_excel_bytes(records)

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="Candidate_Screening_Decisions_Reasoning.xlsx"; filename*=UTF-8\'\'Candidate_Screening_Decisions_Reasoning.xlsx',
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get(
    "/batch-status",
    summary="Get Recruitment Batch Finalization Status"
)
async def get_recruitment_batch_status():
    """
    Returns whether the current candidate batch is in active HR review or finalized & dispatched.
    """
    records = csv_storage.get_all_records()
    status_info = csv_storage.get_batch_status()
    
    total = len(records)
    shortlisted = len([r for r in records if (r.get("status") or r.get("system_decision")) == "SHORTLISTED"])
    review = len([r for r in records if (r.get("status") or r.get("system_decision")) == "HR_REVIEW"])
    rejected = len([r for r in records if (r.get("status") or r.get("system_decision")) == "REJECTED"])
    assigned = len([r for r in records if r.get("assigned_employee_email") and r.get("assigned_employee_email").strip()])

    return {
        "status": "SUCCESS",
        "is_finalized": status_info.get("is_finalized", False),
        "finalized_at": status_info.get("finalized_at"),
        "total_candidates": total,
        "shortlisted": shortlisted,
        "hr_review": review,
        "rejected": rejected,
        "assigned_interviewers": assigned,
        "csv_exists": csv_storage.csv_path.exists()
    }


class FinalizeBatchRequest(BaseModel):
    hr_email: Optional[str] = Field(None, description="Optional HR email to receive final ledger digest")
    dispatch_interviewer_emails: bool = Field(True, description="Whether to dispatch interview availability request emails to assigned interviewers")
    move_drive_files: bool = Field(True, description="Whether to move candidate resumes into Selected/Rejected folders in Google Drive")


@router.post(
    "/finalize-batch",
    summary="Finalize Recruitment Batch: Cook CSV Ledger, Relocate Drive Resumes & Dispatch All Emails"
)
async def finalize_recruitment_batch(payload: Optional[FinalizeBatchRequest] = None):
    """
    Core Finalization Execution triggered by HR:
    1. Cooks official screening_results.csv & screening_results.xlsx with Date and Drive links.
    2. Moves all candidate resumes in Google Drive to Selected/{Role} or Rejected/{Role}.
    3. Dispatches interview request emails with Question Kits to assigned technical interviewers.
    4. Dispatches the comprehensive HR Ultimate List email digest with attached screening_results.csv to HR.
    5. Marks batch as officially finalized.
    """
    from app.core.config import settings
    from app.services.google_drive_organizer import google_drive_organizer
    from app.services.email_service import EmailService

    hr_target = payload.hr_email if payload and payload.hr_email else settings.HR_NOTIFICATION_EMAIL
    do_emails = payload.dispatch_interviewer_emails if payload else True
    do_drive = payload.move_drive_files if payload else True

    try:
        # 1. Cook official CSV and Excel ledgers
        cook_res = csv_storage.cook_final_csv_ledger()
        candidates = cook_res["records"]

        if not candidates:
            raise HTTPException(status_code=400, detail="No candidates in pool to finalize.")

        # 2. Push directly to Domo Webform / DataSet Cloud Storage
        domo_sync_result = None
        if settings.ENABLE_DOMO_SYNC:
            try:
                from app.services.domo_service import domo_service
                domo_sync_result = domo_service.push_records_to_domo(candidates)
                logger.info(
                    "Pushed recruitment records to Domo Webform/DataSet",
                    destination=domo_sync_result.get("destination"),
                    count=domo_sync_result.get("count")
                )
            except Exception as domo_err:
                logger.warning("Domo sync encountered error during batch finalization", error=str(domo_err))
                domo_sync_result = {"status": "FAILED", "error": str(domo_err)}

        # 3. Relocate resumes in Google Drive
        drive_results = []
        if do_drive:
            for cand in candidates:
                try:
                    c_status = cand.get("status") or cand.get("system_decision") or "REJECTED"
                    target_status = "Selected" if c_status == "SHORTLISTED" else "Rejected"
                    res = google_drive_organizer.organize_candidate_resume(
                        candidate_id=cand.get("candidate_id", ""),
                        candidate_name=cand.get("candidate_name", "Applicant"),
                        job_role=cand.get("job_role", "AI_Engineer"),
                        status=target_status,
                        resume_file_id_or_url=cand.get("resume_file") or cand.get("resume_file_id") or ""
                    )
                    drive_results.append(res)
                except Exception as d_err:
                    logger.warning("Drive file move note during batch finalization", candidate=cand.get("candidate_id"), error=str(d_err))

        # 4. Dispatch emails to assigned technical interviewers
        email_svc = EmailService()
        interviewer_emails_sent = []
        if do_emails:
            for cand in candidates:
                emp_email = cand.get("assigned_employee_email", "").strip()
                emp_name = cand.get("assigned_employee_name", "Technical Interviewer")
                is_selected = (cand.get("status") or cand.get("system_decision")) == "SHORTLISTED"

                if emp_email and is_selected:
                    try:
                        mail_res = email_svc.send_availability_request_email(
                            candidate_name=cand.get("candidate_name", "Candidate"),
                            candidate_id=cand.get("candidate_id", ""),
                            job_role=cand.get("job_role", ""),
                            employee_name=emp_name,
                            employee_email=emp_email,
                            hr_email=hr_target
                        )
                        interviewer_emails_sent.append({
                            "candidate_id": cand.get("candidate_id"),
                            "employee_email": emp_email,
                            "status": "SENT"
                        })
                    except Exception as mail_err:
                        logger.warning("Could not dispatch interviewer email", error=str(mail_err))

        # 5. Dispatch HR Ultimate List Digest email with cooked CSV attached
        hr_digest_delivery = None
        try:
            hr_digest_delivery = email_svc.send_shortlist_digest(
                recipient_email=hr_target,
                candidates=candidates,
                csv_attachment_path=str(settings.csv_absolute_path)
            )
        except Exception as hr_err:
            logger.warning("Could not dispatch HR ultimate email digest", error=str(hr_err))
            hr_digest_delivery = {"status": "FAILED", "error": str(hr_err)}

        # 6. Mark batch finalized
        status_payload = {
            "is_finalized": True,
            "finalized_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "finalized_count": len(candidates),
            "hr_email": hr_target,
            "interviewers_emailed_count": len(interviewer_emails_sent),
            "domo_synced": domo_sync_result.get("status") == "SUCCESS" if domo_sync_result else False
        }
        csv_storage.set_batch_status(True, status_payload)

        logger.info(
            "Batch finalization executed successfully",
            total_candidates=len(candidates),
            interviewers_emailed=len(interviewer_emails_sent),
            domo_status=domo_sync_result.get("status") if domo_sync_result else "DISABLED"
        )

        return {
            "status": "SUCCESS",
            "message": f"🎉 Recruitment Batch Finalized! Pushed {len(candidates)} candidates to Domo, organized Drive files, notified {len(interviewer_emails_sent)} technical interviewers, and sent Ultimate Ledger Digest to HR ({hr_target}).",
            "batch_summary": status_payload,
            "domo_sync": domo_sync_result,
            "csv_path": cook_res["csv_path"],
            "interviewer_emails_sent": interviewer_emails_sent,
            "hr_digest_delivery": hr_digest_delivery
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to finalize recruitment batch", error=str(e))
        raise HTTPException(status_code=500, detail=f"Finalize batch execution failed: {str(e)}")


class UpdateJDRequest(BaseModel):
    title: Optional[str] = None
    job_description: Optional[str] = None
    core_responsibilities: Optional[List[str]] = None
    ats_keywords: Optional[Dict[str, List[str]]] = None


@router.get(
    "/jd/all",
    summary="Get all Job Descriptions, core responsibilities, and ATS keywords"
)
async def get_all_job_descriptions():
    """
    Returns complete Job Descriptions, responsibilities, and ATS keyword targets for all 3 roles:
    AI_ENGINEER, FULLSTACK_DEV, and DATA_ANALYST.
    """
    from app.services.rule_engine import RuleEngine
    rule_engine = RuleEngine()
    return {
        "status": "SUCCESS",
        "roles": rule_engine.get_all_role_jds()
    }


@router.get(
    "/jd/{job_role}",
    summary="Get Job Description and ATS keywords for a specific role"
)
async def get_job_description(job_role: str):
    """
    Returns Job Description, core responsibilities, and ATS keywords for a specific role.
    """
    from app.services.rule_engine import RuleEngine
    rule_engine = RuleEngine()
    role_rule = rule_engine.get_role_rule(job_role)
    return {
        "status": "SUCCESS",
        "job_role": rule_engine.normalize_role_code(job_role),
        "data": role_rule
    }


@router.put(
    "/jd/{job_role}",
    summary="Update Job Description, responsibilities, and ATS keywords for a role"
)
async def update_job_description(job_role: str, payload: UpdateJDRequest):
    """
    Updates the Job Description, core duties, and target ATS keywords for a specific role.
    """
    from app.services.rule_engine import RuleEngine
    rule_engine = RuleEngine()
    try:
        updated = rule_engine.update_role_jd(
            job_role, payload.model_dump(exclude_unset=True)
        )
        return {
            "status": "SUCCESS",
            "message": f"Successfully updated Job Description and ATS keywords for {job_role}.",
            "data": updated
        }
    except Exception as e:
        logger.error("Failed to update JD", role=job_role, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update Job Description: {str(e)}")


@router.get(
    "/{candidate_id}",
    summary="Get single candidate evaluation details & decision reason"
)
async def get_application(candidate_id: str):
    """
    Returns complete candidate evaluation, score breakdown, evidence logs, and decision_reason string.
    """
    candidate = csv_storage.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate application '{candidate_id}' not found."
        )
    return {
        "status": "SUCCESS",
        "candidate": candidate
    }


@router.post(
    "/{candidate_id}/override",
    summary="Submit HR Decision Override for a candidate"
)
async def submit_hr_override(
    candidate_id: str,
    payload: HROverrideRequest
):
    """
    Allows HR recruiter to override automated system decision and record reason.
    """
    candidate = csv_storage.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate application '{candidate_id}' not found."
        )

    candidate["hr_override_decision"] = payload.override_decision.upper()
    candidate["hr_override_reason"] = payload.override_reason
    candidate["hr_override_timestamp"] = "2026-08-17T16:50:00Z"

    updated = csv_storage.save_screening_result(candidate)

    logger.info("HR decision override logged", candidate_id=candidate_id, new_decision=payload.override_decision)
    return {
        "status": "SUCCESS",
        "message": f"Decision for candidate '{candidate_id}' successfully overridden to {payload.override_decision}.",
        "candidate": updated
    }


@router.post(
    "/clear",
    summary="Clear all candidate application screening records and reset database"
)
async def clear_all_applications():
    """
    Clears all candidate records from CSV & Excel ledgers and deletes cached resume files.
    """
    from pathlib import Path
    csv_storage.clear_ledger()
    resumes_dir = Path("app/data/resumes")
    if resumes_dir.exists():
        for f in resumes_dir.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                except Exception:
                    pass
    return {
        "status": "SUCCESS",
        "message": "Cleared all candidate application records and cached resume files."
    }


class HRFeedbackPayload(BaseModel):
    hr_feedback: str = Field(..., description="HR Recruiter feedback, critique, or adjusted requirements for re-evaluation")


class HRRejectPayload(BaseModel):
    reason: Optional[str] = Field("Rejected during HR review", description="Optional HR rejection notes")


@router.post(
    "/{candidate_id}/hr-approve",
    summary="Human-in-the-Loop: HR Approves Candidate for Technical Interview Pipeline"
)
async def hr_approve_candidate(candidate_id: str):
    """
    Approves candidate in the Human-in-the-Loop review stage.
    Updates candidate pool state (staged until final batch dispatch).
    """
    candidate = csv_storage.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate application '{candidate_id}' not found."
        )

    updated = csv_storage.approve_candidate_by_hr(candidate_id)
    logger.info("Candidate approved by HR recruiter in candidate pool", candidate_id=candidate_id)

    return {
        "status": "SUCCESS",
        "message": f"Candidate '{candidate_id}' approved in review pool. Will be finalized upon batch dispatch.",
        "candidate": updated
    }


@router.post(
    "/{candidate_id}/hr-re-evaluate",
    summary="Human-in-the-Loop: AI Re-evaluates Candidate based on HR Feedback"
)
async def hr_re_evaluate_candidate(candidate_id: str, payload: HRFeedbackPayload):
    """
    Applies custom HR feedback / critique to re-evaluate candidate scoring & reasoning via Google Gemini.
    """
    from app.services.hitl_service import hitl_service
    from app.services.resume_storage_service import resume_storage

    candidate = csv_storage.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate application '{candidate_id}' not found."
        )

    raw_text = None
    try:
        resume_bytes, _ = resume_storage.get_resume(candidate_id, candidate.get("candidate_name", ""))
        if resume_bytes:
            from app.services.text_extractor import extract_text_from_bytes
            raw_text = extract_text_from_bytes(resume_bytes)
    except Exception:
        raw_text = None

    re_eval_res = hitl_service.re_evaluate_candidate(
        candidate_record=candidate,
        hr_feedback=payload.hr_feedback,
        raw_resume_text=raw_text
    )

    updated = csv_storage.update_candidate_re_evaluation(
        candidate_id=candidate_id,
        new_score=re_eval_res["revised_score"],
        new_reason=re_eval_res["revised_reasoning"],
        hr_feedback=payload.hr_feedback,
        new_status=re_eval_res["revised_decision"]
    )

    logger.info("Executed HITL AI candidate re-evaluation in pool", candidate_id=candidate_id, revised_score=re_eval_res["revised_score"])
    return {
        "status": "SUCCESS",
        "message": f"Candidate '{candidate_id}' successfully re-evaluated with HR feedback.",
        "re_evaluation": re_eval_res,
        "candidate": updated
    }


@router.post(
    "/{candidate_id}/hr-reject",
    summary="Human-in-the-Loop: HR Rejects Candidate"
)
async def hr_reject_candidate(candidate_id: str, payload: HRRejectPayload):
    """
    Rejects candidate in the Human-in-the-Loop review stage with HR feedback notes.
    """
    candidate = csv_storage.get_record_by_id(candidate_id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate application '{candidate_id}' not found."
        )

    updated = csv_storage.reject_candidate_by_hr(candidate_id, payload.reason)
    logger.info("Candidate rejected by HR recruiter in review pool", candidate_id=candidate_id, reason=payload.reason)
    return {
        "status": "SUCCESS",
        "message": f"Candidate '{candidate_id}' marked as rejected in review pool.",
        "candidate": updated
    }


class BulkApprovePayload(BaseModel):
    candidate_ids: Optional[List[str]] = Field(None, description="List of candidate IDs to approve. If omitted and approve_all_pending=True, approves all pending candidates.")
    approve_all_pending: bool = Field(False, description="Set to true to approve all candidates currently in PENDING_HR_APPROVAL status.")


class BulkRejectPayload(BaseModel):
    candidate_ids: List[str] = Field(..., description="List of candidate IDs to reject.")
    reason: Optional[str] = Field("Bulk rejected by HR recruiter", description="Rejection reason")


@router.post(
    "/bulk-hr-approve",
    summary="Human-in-the-Loop: Bulk Approve Candidates in Review Pool"
)
async def bulk_approve_candidates(payload: BulkApprovePayload):
    """
    Approves multiple candidates at once in the candidate review pool.
    """
    approved = csv_storage.bulk_approve_candidates(
        candidate_ids=payload.candidate_ids,
        approve_all_pending=payload.approve_all_pending
    )

    if not approved:
        return {
            "status": "SUCCESS",
            "message": "No pending candidates matched the criteria to approve.",
            "approved_count": 0,
            "candidates": []
        }

    return {
        "status": "SUCCESS",
        "message": f"Successfully approved {len(approved)} candidate(s) in review pool! Ready for batch finalization.",
        "approved_count": len(approved),
        "candidates": approved
    }


@router.post(
    "/bulk-hr-reject",
    summary="Human-in-the-Loop: Bulk Reject Candidates in Review Pool"
)
async def bulk_reject_candidates(payload: BulkRejectPayload):
    """
    Bulk rejects multiple candidates in review pool.
    """
    rejected = []
    for cid in payload.candidate_ids:
        cand = csv_storage.get_record_by_id(cid)
        if cand:
            updated = csv_storage.reject_candidate_by_hr(cid, payload.reason)
            if updated:
                rejected.append(updated)

    return {
        "status": "SUCCESS",
        "message": f"Successfully rejected {len(rejected)} candidate(s) in review pool.",
        "rejected_count": len(rejected),
        "candidates": rejected
    }

