import pytest
from app.services.rule_engine import RuleEngine
from app.schemas.candidate import StructuredCandidateProfile, CandidateContact, SkillItem


def create_mock_candidate(email: str, skills: list, exp_years: float) -> StructuredCandidateProfile:
    return StructuredCandidateProfile(
        candidate=CandidateContact(full_name="Test Candidate", email=email),
        total_years_experience=exp_years,
        skills=[SkillItem(name=s, evidence_snippet=f"Experienced in {s}") for s in skills]
    )


def test_mandatory_criteria_pass_ai_engineer():
    rule_engine = RuleEngine()
    candidate = create_mock_candidate("ai.dev@example.com", ["Python", "PyTorch", "FastAPI"], exp_years=3.0)

    passed, passed_checks, failures = rule_engine.evaluate_mandatory_criteria(candidate, "AI_ENGINEER")

    assert passed is True
    assert len(failures) == 0
    assert len(passed_checks) == 2


def test_mandatory_criteria_fail_experience_fullstack_dev():
    rule_engine = RuleEngine()
    # Full Stack Dev requires 2.0 years experience
    candidate = create_mock_candidate("junior@example.com", ["React", "Node.js"], exp_years=0.8)

    passed, passed_checks, failures = rule_engine.evaluate_mandatory_criteria(candidate, "FULLSTACK_DEV")

    assert passed is False
    assert len(failures) == 1
    assert "Required 2.0 years, candidate has 0.8 years" in failures[0]



def test_mandatory_criteria_fail_missing_skill_data_analyst():
    rule_engine = RuleEngine()
    # Data Analyst requires SQL
    candidate = create_mock_candidate("analyst@example.com", ["Tableau", "Excel"], exp_years=3.0)

    passed, passed_checks, failures = rule_engine.evaluate_mandatory_criteria(candidate, "DATA_ANALYST")

    assert passed is False
    assert len(failures) == 1
    assert "Skill 'SQL' not found" in failures[0]
