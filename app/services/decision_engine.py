import structlog
from typing import Dict, Any, Tuple, List
from app.services.rule_engine import RuleEngine
from app.services.scoring_engine import ScoringEngine
from app.services.ats_engine import ATSEngine, ats_engine
from app.schemas.candidate import StructuredCandidateProfile

logger = structlog.get_logger(__name__)

ROLE_DISPLAY_NAMES = {
    "AI_ENGINEER": "AI Engineer",
    "FULLSTACK_DEV": "Full Stack Developer",
    "DATA_ANALYST": "Data Analyst",
    "PYTHON_DEV": "Python Developer"
}


class DecisionEngine:
    """
    Combines Mandatory Criteria Check, Weighted Scoring, and ATS Keyword Analysis
    to output system recommendation and a clear, natural prose statement explaining WHY the candidate
    was selected or rejected without raw numerical score clutter.
    """

    def __init__(
        self,
        rule_engine: RuleEngine = None,
        scoring_engine: ScoringEngine = None,
        ats_scoring_engine: ATSEngine = None
    ):
        self.rule_engine = rule_engine or RuleEngine()
        self.scoring_engine = scoring_engine or ScoringEngine(self.rule_engine)
        self.ats_scoring_engine = ats_scoring_engine or ats_engine

    def evaluate_candidate(
        self,
        profile: StructuredCandidateProfile,
        job_role: str,
        raw_resume_text: str = None
    ) -> Dict[str, Any]:
        """
        Evaluates candidate and returns decision dictionary with natural prose selection reasoning and ATS analysis.
        """
        role_rule = self.rule_engine.get_role_rule(job_role)
        thresholds = role_rule.get("thresholds", {"shortlist": 80, "review": 60})
        role_title = ROLE_DISPLAY_NAMES.get(job_role.upper(), job_role.replace("_", " ").title())

        # 1. Mandatory Checks
        mandatory_passed, passed_checks, mandatory_failures = self.rule_engine.evaluate_mandatory_criteria(
            profile, job_role
        )

        # 2. Weighted Scoring
        weighted_score, score_breakdown, evidence_logs = self.scoring_engine.calculate_score(
            profile, job_role
        )

        # 3. ATS & Job Description Keyword Match Analysis
        ats_res = self.ats_scoring_engine.compute_ats_score(
            profile, job_role, raw_resume_text=raw_resume_text
        )
        ats_score = ats_res.get("ats_score", weighted_score)

        # 4. Decision Logic & Clean Prose Reasoning Generation
        shortlist_threshold = float(thresholds.get("shortlist", 80))
        review_threshold = float(thresholds.get("review", 60))

        # Identify top strengths
        top_cats = [cat for cat, pts in sorted(score_breakdown.items(), key=lambda x: x[1], reverse=True) if pts > 0][:2]
        if top_cats:
            strengths_desc = " and ".join(top_cats)
        else:
            strengths_desc = "the core job technical requirements"

        matched_kws = ats_res.get("matched_keywords", [])
        top_matched_str = ", ".join(matched_kws[:4]) if matched_kws else "core skills"

        if not mandatory_passed:
            system_decision = "REJECTED"
            # Format clean failure statement without raw test tags
            clean_failures = []
            for fail in mandatory_failures:
                f_text = fail.replace("FAIL: ", "")
                clean_failures.append(f_text)
            
            reasons_str = "; ".join(clean_failures)
            reason_summary = f"The candidate was not selected for the {role_title} role because they did not meet the mandatory position requirements ({reasons_str})."

        elif weighted_score >= shortlist_threshold or ats_score >= shortlist_threshold:
            system_decision = "SHORTLISTED"
            reason_summary = f"The candidate was selected for the {role_title} position because they satisfied all mandatory qualifications, scored {ats_score}% ATS match, and demonstrated exceptional hands-on expertise in {strengths_desc} ({top_matched_str})."

        elif weighted_score >= review_threshold or ats_score >= review_threshold:
            system_decision = "HR_REVIEW"
            reason_summary = f"The candidate has been referred for HR manual review ({ats_score}% ATS match). They met all mandatory prerequisites and demonstrated solid knowledge in {strengths_desc}, but secondary recruiter evaluation is recommended."

        else:
            system_decision = "REJECTED"
            # Find missing keywords
            missing_kws = ats_res.get("missing_keywords", [])
            missing_desc = f", particularly missing key skills: {', '.join(missing_kws[:3])}" if missing_kws else ""
            reason_summary = f"The candidate was not selected because their technical profile did not align closely enough with the requirements for the {role_title} position (ATS Match: {ats_score}%){missing_desc}."

        return {
            "job_role": job_role,
            "mandatory_passed": mandatory_passed,
            "mandatory_passed_checks": passed_checks,
            "mandatory_failures": mandatory_failures,
            "weighted_score": weighted_score,
            "score_breakdown": score_breakdown,
            "evidence_logs": evidence_logs,
            "system_decision": system_decision,
            "decision_reason": reason_summary,
            "ats_score": ats_score,
            "keyword_match_percentage": ats_res.get("keyword_match_percentage", 0.0),
            "matched_keywords": ats_res.get("matched_keywords", []),
            "missing_keywords": ats_res.get("missing_keywords", []),
            "ats_breakdown": ats_res.get("ats_breakdown", {}),
            "ats_verdict": ats_res.get("ats_verdict", "MODERATE_MATCH"),
            "ats_verdict_label": ats_res.get("ats_verdict_label", "Moderate ATS Match"),
            "ats_summary": ats_res.get("ats_summary", "")
        }
