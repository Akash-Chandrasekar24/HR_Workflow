import base64
import structlog
from typing import Dict, Any
from app.schemas.application import ApplicationIngestRequest
from app.services.google_drive import GoogleDriveService
from app.services.document_validator import DocumentValidator
from app.services.document_extractor import DocumentExtractor
from app.services.resume_normalizer import ResumeNormalizer
from app.services.resume_parser import GeminiResumeParser, FallbackResumeParser
from app.services.decision_engine import DecisionEngine
from app.services.csv_storage import CSVStorageService

logger = structlog.get_logger(__name__)


class ResumeProcessorService:
    """
    End-to-End Orchestrator for Candidate Resume Screening Pipeline.
    Supports Base64 direct payloads (no Service Account required), Direct HTTP downloads, and GCP Drive API.
    """

    def __init__(
        self,
        drive_service: GoogleDriveService = None,
        llm_parser = None,
        decision_engine: DecisionEngine = None,
        storage_service: CSVStorageService = None
    ):
        self.drive_service = drive_service or GoogleDriveService()
        self.llm_parser = llm_parser or GeminiResumeParser()
        self.decision_engine = decision_engine or DecisionEngine()
        self.storage_service = storage_service or CSVStorageService()

    def process_application(self, payload: ApplicationIngestRequest) -> Dict[str, Any]:
        """
        Executes complete screening pipeline for a candidate submission.
        """
        candidate_id = payload.candidate_id
        file_id = payload.resume_file_id
        job_role = payload.job_role

        logger.info("Starting resume screening pipeline", candidate_id=candidate_id, file_id=file_id, role=job_role)

        try:
            # 1. Retrieve Resume File Bytes (Direct Base64 OR Google Drive Download)
            if payload.resume_base64:
                logger.info("Processing resume from direct Base64 payload (No GCP Service Account required)", candidate_id=candidate_id)
                file_bytes = base64.b64decode(payload.resume_base64)
                filename = payload.resume_filename or f"resume_{file_id}.pdf"
                mime_type = payload.resume_mime_type or "application/pdf"
            else:
                file_bytes, filename, mime_type = self.drive_service.download_file(file_id)

            # 2. Validate File & Compute SHA256 Hash
            is_valid, detected_fmt, file_hash, val_err = DocumentValidator.validate_and_hash(file_bytes, filename)
            if not is_valid:
                error_record = {
                    "candidate_id": candidate_id,
                    "candidate_name": payload.full_name,
                    "email": payload.email,
                    "phone": payload.phone or "",
                    "job_role": job_role,
                    "resume_file_id": file_id,
                    "resume_hash": file_hash,
                    "mandatory_passed": False,
                    "weighted_score": 0.0,
                    "system_decision": "REJECTED",
                    "decision_reason": f"REJECTED: File validation failed ({val_err})",
                    "form_responses": payload.form_responses,
                    "processing_status": "FAILED"
                }
                return self.storage_service.save_screening_result(error_record)

            # Persist local resume copy for interview attachment
            try:
                from app.services.resume_storage_service import resume_storage
                resume_storage.save_resume(candidate_id, payload.full_name, file_bytes, filename)
            except Exception as res_err:
                logger.warning("Could not cache resume locally", error=str(res_err))

            # 3. Extract Text (PDF / DOCX / OCR)
            raw_text, extraction_method = DocumentExtractor.extract_text(file_bytes, detected_fmt)


            # Append custom Google Form Q&A responses to extracted text
            form_qa_lines = []
            if payload.form_responses:
                form_qa_lines.append("\n=== CANDIDATE GOOGLE FORM RESPONSES ===")
                for q, a in payload.form_responses.items():
                    form_qa_lines.append(f"{q}: {a}")
            
            combined_raw_text = raw_text + "\n" + "\n".join(form_qa_lines)

            # 4. Normalize Text
            normalized_text = ResumeNormalizer.normalize_text(combined_raw_text)

            # 5. LLM / Fallback Structured JSON Parsing
            profile = self.llm_parser.parse_resume(normalized_text)
            
            # Enrich profile with form inputs if missing
            if not profile.candidate.full_name or profile.candidate.full_name == "Applicant":
                profile.candidate.full_name = payload.full_name
            if not profile.candidate.email or profile.candidate.email == "applicant@example.com":
                profile.candidate.email = payload.email
            if payload.years_of_experience > profile.total_years_experience:
                profile.total_years_experience = payload.years_of_experience

            # 6. Evaluate Rules, Calculate Score, ATS Keyword Match & Decision
            eval_result = self.decision_engine.evaluate_candidate(
                profile, job_role, raw_resume_text=normalized_text
            )

            # 7. Format complete record for CSV & Domo Ledgers
            screening_record = {
                "candidate_id": candidate_id,
                "timestamp": payload.timestamp,
                "candidate_name": profile.candidate.full_name or payload.full_name,
                "email": profile.candidate.email or payload.email,
                "phone": profile.candidate.phone or payload.phone or "",
                "job_role": job_role,
                "resume_file_id": file_id,
                "resume_hash": file_hash,
                "mandatory_passed": eval_result["mandatory_passed"],
                "weighted_score": eval_result["weighted_score"],
                "ats_score": eval_result.get("ats_score", eval_result["weighted_score"]),
                "keyword_match_percentage": eval_result.get("keyword_match_percentage", 0.0),
                "matched_keywords": eval_result.get("matched_keywords", []),
                "missing_keywords": eval_result.get("missing_keywords", []),
                "ats_breakdown": eval_result.get("ats_breakdown", {}),
                "ats_verdict": eval_result.get("ats_verdict", "MODERATE_MATCH"),
                "ats_verdict_label": eval_result.get("ats_verdict_label", "Moderate ATS Match"),
                "system_decision": eval_result["system_decision"],
                "decision_reason": eval_result["decision_reason"],
                "score_breakdown": eval_result["score_breakdown"],
                "evidence_snippets": eval_result["evidence_logs"],
                "form_responses": payload.form_responses,
                "processing_status": "COMPLETED"
            }

            # 8. Persist to Candidate Pool & Ledger
            saved_record = self.storage_service.save_screening_result(screening_record)
            logger.info("Successfully completed candidate processing", candidate_id=candidate_id, decision=saved_record["system_decision"], ats_score=saved_record.get("ats_score"))
            return saved_record

        except Exception as e:
            logger.error("Error in resume processing pipeline", candidate_id=candidate_id, error=str(e))
            error_record = {
                "candidate_id": candidate_id,
                "candidate_name": payload.full_name,
                "email": payload.email,
                "job_role": job_role,
                "resume_file_id": file_id,
                "mandatory_passed": False,
                "weighted_score": 0.0,
                "system_decision": "REJECTED",
                "decision_reason": f"REJECTED: Pipeline error encountered ({str(e)})",
                "form_responses": payload.form_responses,
                "processing_status": "FAILED"
            }
            return self.storage_service.save_screening_result(error_record)
