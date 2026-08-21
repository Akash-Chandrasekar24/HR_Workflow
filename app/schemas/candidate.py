from typing import List, Optional
from pydantic import BaseModel, Field


class CandidateContact(BaseModel):
    full_name: Optional[str] = Field(None, json_schema_extra={"example": "Akash Chandrasekar"})
    email: Optional[str] = Field(None, json_schema_extra={"example": "akash@example.com"})
    phone: Optional[str] = Field(None, json_schema_extra={"example": "+1-555-0199"})
    location: Optional[str] = Field(None, json_schema_extra={"example": "San Francisco, CA"})


class WorkExperienceItem(BaseModel):
    company: Optional[str] = Field(None, json_schema_extra={"example": "Tech Corp"})
    role: Optional[str] = Field(None, json_schema_extra={"example": "AI Engineer"})
    duration_months: float = Field(0.0, ge=0.0, json_schema_extra={"example": 24.0})
    highlights: List[str] = Field(default_factory=list)


class SkillItem(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Python"})
    evidence_snippet: Optional[str] = Field(None, json_schema_extra={"example": "Developed FastAPI microservices for 2 years"})
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class EducationItem(BaseModel):
    degree: Optional[str] = Field(None, json_schema_extra={"example": "Bachelor of Science"})
    field: Optional[str] = Field(None, json_schema_extra={"example": "Computer Science"})
    institution: Optional[str] = Field(None, json_schema_extra={"example": "Stanford University"})
    graduation_year: Optional[int] = Field(None, json_schema_extra={"example": 2022})


class StructuredCandidateProfile(BaseModel):
    candidate: CandidateContact
    total_years_experience: float = Field(0.0, ge=0.0, json_schema_extra={"example": 2.5})
    work_experience: List[WorkExperienceItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
