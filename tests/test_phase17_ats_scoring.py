import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.candidate import StructuredCandidateProfile, CandidateContact, SkillItem, WorkExperienceItem
from app.services.ats_engine import ATSEngine
from app.services.decision_engine import DecisionEngine
from app.services.rule_engine import RuleEngine

client = TestClient(app)


def test_ats_scoring_high_match_ai_engineer():
    engine = ATSEngine()
    profile = StructuredCandidateProfile(
        candidate=CandidateContact(
            full_name="Aarav Sharma",
            email="aarav@example.com",
            phone="+91-9876543210"
        ),
        total_years_experience=3.5,
        skills=[
            SkillItem(name="Python", evidence_snippet="5 years Python backend development", confidence=1.0),
            SkillItem(name="PyTorch", evidence_snippet="Built CNN and Transformer models in PyTorch", confidence=1.0),
            SkillItem(name="TensorFlow", evidence_snippet="Trained deep neural networks", confidence=1.0),
            SkillItem(name="Machine Learning", evidence_snippet="End to end ML pipelines", confidence=1.0),
            SkillItem(name="Deep Learning", evidence_snippet="Vision and NLP architectures", confidence=1.0),
            SkillItem(name="LLM", evidence_snippet="Fine-tuned Llama 3 models", confidence=1.0),
            SkillItem(name="RAG", evidence_snippet="Built production RAG system with ChromaDB", confidence=1.0),
            SkillItem(name="LangChain", evidence_snippet="Constructed agent workflows", confidence=1.0),
            SkillItem(name="FastAPI", evidence_snippet="Deployed microservices", confidence=1.0),
            SkillItem(name="Docker", evidence_snippet="Containerized AI solutions", confidence=1.0)
        ],
        work_experience=[
            WorkExperienceItem(
                company="AI Labs",
                role="Senior AI Engineer",
                duration_months=36.0,
                highlights=[
                    "Architected and implemented production-grade Retrieval-Augmented Generation (RAG) pipelines",
                    "Fine-tuned large language models (LLMs) using PyTorch and Hugging Face",
                    "Deployed low-latency AI microservices using Docker and FastAPI"
                ]
            )
        ]
    )

    ats_res = engine.compute_ats_score(profile, "AI_ENGINEER")

    assert ats_res["ats_score"] >= 80.0
    assert ats_res["ats_verdict"] == "STRONG_MATCH"
    assert "Python" in ats_res["matched_keywords"]
    assert "PyTorch" in ats_res["matched_keywords"]
    assert "RAG" in ats_res["matched_keywords"]
    assert len(ats_res["missing_mandatory"]) == 0


def test_ats_scoring_missing_skills_detection():
    engine = ATSEngine()
    # Candidate with only basic SQL
    profile = StructuredCandidateProfile(
        candidate=CandidateContact(
            full_name="John Doe",
            email="john@example.com"
        ),
        total_years_experience=0.5,
        skills=[
            SkillItem(name="SQL", confidence=1.0)
        ]
    )

    ats_res = engine.compute_ats_score(profile, "AI_ENGINEER")

    assert ats_res["ats_score"] < 60.0
    assert ats_res["ats_verdict"] == "LOW_MATCH"
    assert "Python" in ats_res["missing_mandatory"]
    assert "PyTorch" in ats_res["missing_mandatory"]


def test_decision_engine_with_ats_integration():
    decision_engine = DecisionEngine()
    profile = StructuredCandidateProfile(
        candidate=CandidateContact(
            full_name="Priya Patel",
            email="priya@example.com"
        ),
        total_years_experience=4.0,
        skills=[
            SkillItem(name="JavaScript", confidence=1.0),
            SkillItem(name="TypeScript", confidence=1.0),
            SkillItem(name="React", confidence=1.0),
            SkillItem(name="Node.js", confidence=1.0),
            SkillItem(name="Python", confidence=1.0),
            SkillItem(name="SQL", confidence=1.0),
            SkillItem(name="Next.js", confidence=1.0),
            SkillItem(name="PostgreSQL", confidence=1.0),
            SkillItem(name="Docker", confidence=1.0)
        ],
        work_experience=[
            WorkExperienceItem(
                company="Tech Co",
                role="Full Stack Engineer",
                duration_months=48.0,
                highlights=[
                    "Design and implement responsive UI components using React and Next.js",
                    "Architect and maintain RESTful APIs using Node.js and FastAPI"
                ]
            )
        ]
    )

    result = decision_engine.evaluate_candidate(profile, "FULLSTACK_DEV")

    assert result["mandatory_passed"] is True
    assert result["system_decision"] == "SHORTLISTED"
    assert result["ats_score"] >= 80.0
    assert "matched_keywords" in result
    assert "ats_breakdown" in result
    assert "Full Stack Developer" in result["decision_reason"]


def test_jd_api_endpoints():
    # 1. GET /api/v1/applications/jd/all
    res = client.get("/api/v1/applications/jd/all")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "AI_ENGINEER" in data["roles"]
    assert "FULLSTACK_DEV" in data["roles"]
    assert "DATA_ANALYST" in data["roles"]

    # 2. GET /api/v1/applications/jd/AI_ENGINEER
    res_single = client.get("/api/v1/applications/jd/AI_ENGINEER")
    assert res_single.status_code == 200
    data_single = res_single.json()
    assert data_single["status"] == "SUCCESS"
    assert "job_description" in data_single["data"]
    assert "core_responsibilities" in data_single["data"]
    assert "ats_keywords" in data_single["data"]

    # 3. PUT /api/v1/applications/jd/DATA_ANALYST
    update_payload = {
        "title": "Senior Data Analyst",
        "job_description": "Updated Job Description for Data Analyst role.",
        "core_responsibilities": ["Build PowerBI and Tableau dashboards", "Execute complex SQL queries"],
        "ats_keywords": {
            "mandatory_keywords": ["SQL", "Tableau", "Power BI"],
            "preferred_keywords": ["Python", "Pandas", "Looker"],
            "good_to_have_keywords": ["Snowflake", "ETL"]
        }
    }
    res_put = client.put("/api/v1/applications/jd/DATA_ANALYST", json=update_payload)
    assert res_put.status_code == 200
    put_data = res_put.json()
    assert put_data["status"] == "SUCCESS"
    assert put_data["data"]["title"] == "Senior Data Analyst"
