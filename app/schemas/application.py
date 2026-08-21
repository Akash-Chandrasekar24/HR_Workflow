from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ApplicationIngestRequest(BaseModel):
    candidate_id: str = Field(..., json_schema_extra={"example": "CAN-2026-00101"})
    timestamp: Optional[str] = Field(None, json_schema_extra={"example": "2026-08-17T14:30:00Z"})
    full_name: str = Field(default="Applicant", json_schema_extra={"example": "Akash Chandrasekar"})
    email: str = Field(default="applicant@example.com", json_schema_extra={"example": "akash@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+1-555-0199"})
    location: Optional[str] = Field(None, json_schema_extra={"example": "San Francisco, CA"})
    job_role: str = Field(default="PYTHON_DEV", json_schema_extra={"example": "PYTHON_DEV"}, description="Job role code: PYTHON_DEV, AI_ENGINEER, FULLSTACK_DEV, DATA_ANALYST")
    years_of_experience: float = Field(default=0.0, ge=0.0, json_schema_extra={"example": 3.5})
    resume_file_id: str = Field(..., json_schema_extra={"example": "1A2b3C4d5E6f7G8h9I0jK_GoogleDriveFileId"})
    form_response_id: str = Field(default="RESP-001", json_schema_extra={"example": "RESP-987654321"})
    
    # Optional Base64 file bytes passed directly by Google Apps Script (Bypasses Google Service Account!)
    resume_base64: Optional[str] = Field(None, description="Base64 encoded PDF/DOCX file bytes sent directly from Apps Script")
    resume_filename: Optional[str] = Field(None, json_schema_extra={"example": "resume.pdf"})
    resume_mime_type: Optional[str] = Field(None, json_schema_extra={"example": "application/pdf"})

    # Dynamic Form Responses dictionary for custom questions
    form_responses: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ApplicationIngestResponse(BaseModel):
    status: str = "ACCEPTED"
    candidate_id: str
    message: str = "Application metadata received successfully. Resume processing enqueued."
    processing_status: str = "PENDING"
