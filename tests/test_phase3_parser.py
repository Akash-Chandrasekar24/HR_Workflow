import pytest
from app.services.resume_parser import FallbackResumeParser
from app.schemas.candidate import StructuredCandidateProfile


def test_fallback_resume_parser_extraction():
    raw_text = """
    Akash Chandrasekar
    Email: akash.dev@example.com
    Phone: +1-555-0199

    SUMMARY
    Senior AI Engineer with 3.5 years of experience building production LLM services and FastAPI microservices.

    SKILLS
    Python, FastAPI, PyTorch, PostgreSQL, Docker, GCP, RAG

    WORK EXPERIENCE
    AI Engineer - Tech Solutions (2022 - Present)
    - Architected RAG workflows and FastAPI backend applications using Python and PostgreSQL.

    EDUCATION
    Bachelor of Technology in Computer Science, 2022
    """

    parser = FallbackResumeParser()
    profile = parser.parse_resume(raw_text)

    assert isinstance(profile, StructuredCandidateProfile)
    assert profile.candidate.email == "akash.dev@example.com"
    assert profile.total_years_experience == 3.5

    # Verify skill extraction and evidence snippet attachment
    skill_names = [s.name for s in profile.skills]
    assert "Python" in skill_names
    assert "FastAPI" in skill_names
    assert "PostgreSQL" in skill_names

    # Check evidence snippet
    python_skill = next(s for s in profile.skills if s.name == "Python")
    assert python_skill.evidence_snippet is not None
    assert len(python_skill.evidence_snippet) > 0


def test_zero_hallucination_empty_skills():
    raw_text = """
    Jane Doe
    Email: jane@example.com
    Phone: +1-555-0000

    SUMMARY
    Customer Service Specialist with 1 year of experience.
    """

    parser = FallbackResumeParser()
    profile = parser.parse_resume(raw_text)

    skill_names = [s.name for s in profile.skills]
    assert "PyTorch" not in skill_names
    assert "Docker" not in skill_names
    assert "FastAPI" not in skill_names
