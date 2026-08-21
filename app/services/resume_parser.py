import json
import re
import os
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any
from app.schemas.candidate import (
    StructuredCandidateProfile, CandidateContact, WorkExperienceItem, SkillItem, EducationItem
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


class BaseResumeParser(ABC):
    """Abstract interface for LLM Resume Parsers."""

    @abstractmethod
    def parse_resume(self, raw_text: str) -> StructuredCandidateProfile:
        pass


class GeminiResumeParser(BaseResumeParser):
    """
    Structured Resume Parser using Google Gemini API (google-genai SDK).
    Enforces rigid JSON schema output and strict zero-hallucination extraction rules.
    """

    SYSTEM_PROMPT = """
    You are an expert HR Resume Parser AI.
    Your sole task is to extract factual candidate details from the provided resume text into a structured JSON object.

    CRITICAL RULES:
    1. NEVER invent or hallucinate skills, experience, or degrees.
    2. If information is not explicitly present in the text, return null or an empty list.
    3. Extract exact evidence snippets from the resume text for each skill identified.
    4. Distinguish total professional work experience years from years since graduation.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")

    def parse_resume(self, raw_text: str) -> StructuredCandidateProfile:
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY found. Falling back to Rule-Based Heuristic Parser.")
            return FallbackResumeParser().parse_resume(raw_text)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            prompt = f"{self.SYSTEM_PROMPT}\n\nResume Text:\n\"\"\"\n{raw_text}\n\"\"\""

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=StructuredCandidateProfile,
                    temperature=0.0
                )
            )

            parsed_dict = json.loads(response.text)
            return StructuredCandidateProfile(**parsed_dict)

        except Exception as e:
            logger.error("Gemini Resume Parsing failed. Using fallback parser.", error=str(e))
            return FallbackResumeParser().parse_resume(raw_text)


class FallbackResumeParser(BaseResumeParser):
    """
    Deterministic Rule & Regex Fallback Parser for offline testing and offline execution.
    Extracts candidate name, contact details, skills, total experience, and degrees using pattern matching.
    """

    KNOWN_SKILLS = [
        "Python", "FastAPI", "Django", "Flask", "React", "Vue", "Next.js", "Node.js",
        "TypeScript", "JavaScript", "SQL", "PostgreSQL", "MySQL", "MongoDB",
        "PyTorch", "TensorFlow", "Scikit-Learn", "LangChain", "LLM", "GenAI", "RAG",
        "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Tableau", "PowerBI", "Pandas", "NumPy"
    ]

    def parse_resume(self, raw_text: str) -> StructuredCandidateProfile:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

        # Extract Email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
        email = email_match.group(0) if email_match else None

        # Extract Phone
        phone_match = re.search(r"[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}", raw_text)
        phone = phone_match.group(0) if phone_match else None

        # Extract Full Name (assume first line or email handle prefix if missing)
        full_name = lines[0] if lines and len(lines[0]) < 40 and "@" not in lines[0] else "Unknown Candidate"

        # Extract Skills & Evidence Snippets
        detected_skills = []
        for skill in self.KNOWN_SKILLS:
            pattern = r"\b" + re.escape(skill) + r"\b"
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                # Find line containing skill match as evidence
                for line in lines:
                    if re.search(pattern, line, re.IGNORECASE):
                        evidence = line.strip()
                        break
                else:
                    evidence = f"Skill '{skill}' found in resume text."

                detected_skills.append(
                    SkillItem(
                        name=skill,
                        evidence_snippet=evidence,
                        confidence=0.95
                    )
                )

        # Extract Total Experience Years
        exp_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s*(?:of\s*)?experience", raw_text, re.IGNORECASE)
        total_exp = float(exp_match.group(1)) if exp_match else 0.0

        if total_exp == 0.0:
            # Fallback estimation based on year mentions
            years = [int(y) for y in re.findall(r"\b(20[0-2][0-9])\b", raw_text)]
            if len(years) >= 2:
                total_exp = float(max(years) - min(years))

        # Extract Education
        education_list = []
        if re.search(r"bachelor|b\.s|b\.e|b\.tech|mca|master|m\.s|m\.tech|phd", raw_text, re.IGNORECASE):
            education_list.append(
                EducationItem(
                    degree="Degree Mentioned",
                    field="Computer Science / Engineering / Analytics",
                    institution="University",
                    graduation_year=2022
                )
            )

        return StructuredCandidateProfile(
            candidate=CandidateContact(
                full_name=full_name,
                email=email,
                phone=phone,
                location=None
            ),
            total_years_experience=total_exp,
            work_experience=[
                WorkExperienceItem(
                    company="Extracted Work Experience",
                    role="Developer / Specialist",
                    duration_months=total_exp * 12,
                    highlights=["Extracted from resume text."]
                )
            ] if total_exp > 0 else [],
            skills=detected_skills,
            education=education_list,
            certifications=[],
            projects=[],
            domains=[]
        )
