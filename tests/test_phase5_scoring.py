import pytest
from app.services.decision_engine import DecisionEngine
from app.schemas.candidate import (
    StructuredCandidateProfile, CandidateContact, SkillItem, EducationItem, WorkExperienceItem
)


def test_decision_shortlisted_fullstack_dev():
    engine = DecisionEngine()
    candidate = StructuredCandidateProfile(
        candidate=CandidateContact(full_name="Akash", email="akash@example.com"),
        total_years_experience=3.0,
        skills=[
            SkillItem(name="React", evidence_snippet="Built frontend UI using React and TypeScript"),
            SkillItem(name="Node.js", evidence_snippet="Built REST APIs using Node.js & Python FastAPI"),
            SkillItem(name="FastAPI", evidence_snippet="Async backend microservices"),
            SkillItem(name="PostgreSQL", evidence_snippet="Optimized PostgreSQL database queries"),
            SkillItem(name="SQL", evidence_snippet="Database management"),
            SkillItem(name="Docker", evidence_snippet="Containerized app deployment on AWS"),
            SkillItem(name="REST", evidence_snippet="API design")
        ],
        education=[
            EducationItem(degree="Bachelor of Science", field="Computer Science", graduation_year=2022)
        ],
        work_experience=[
            WorkExperienceItem(company="Tech Corp", role="Full Stack Developer", duration_months=36, highlights=["Software Engineering"])
        ]
    )

    result = engine.evaluate_candidate(candidate, "FULLSTACK_DEV")

    assert result["mandatory_passed"] is True
    assert result["weighted_score"] >= 80.0
    assert result["system_decision"] == "SHORTLISTED"
    assert "selected" in result["decision_reason"].lower()



def test_decision_rejected_mandatory_failure():
    engine = DecisionEngine()
    candidate = StructuredCandidateProfile(
        candidate=CandidateContact(full_name="Bob", email="bob@example.com"),
        total_years_experience=0.5,
        skills=[SkillItem(name="HTML", evidence_snippet="Basic HTML")]
    )

    result = engine.evaluate_candidate(candidate, "PYTHON_DEV")

    assert result["mandatory_passed"] is False
    assert result["system_decision"] == "REJECTED"
    assert "not selected" in result["decision_reason"].lower()
    assert len(result["mandatory_failures"]) > 0


def test_decision_hr_review_score():
    engine = DecisionEngine()
    candidate = StructuredCandidateProfile(
        candidate=CandidateContact(full_name="Charlie", email="charlie@example.com"),
        total_years_experience=2.0,
        skills=[
            SkillItem(name="Python", evidence_snippet="Python developer")
        ]
    )

    result = engine.evaluate_candidate(candidate, "AI_ENGINEER")

    assert result["mandatory_passed"] is True
    assert result["system_decision"] in ["HR_REVIEW", "REJECTED"]
    assert "decision_reason" in result
