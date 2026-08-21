import structlog
from typing import Dict, Any, Tuple, List
from app.schemas.candidate import StructuredCandidateProfile
from app.services.rule_engine import RuleEngine

logger = structlog.get_logger(__name__)


class ScoringEngine:
    """
    Deterministic Weighted Scoring Engine.
    Calculates score breakdown (0-100 pts) based on matched skills, keywords, and experience depth.
    """

    def __init__(self, rule_engine: RuleEngine = None):
        self.rule_engine = rule_engine or RuleEngine()

    def calculate_score(
        self,
        profile: StructuredCandidateProfile,
        job_role: str
    ) -> Tuple[float, Dict[str, float], Dict[str, List[str]]]:
        """
        Calculates weighted category scores.
        Returns: (total_weighted_score, score_breakdown, evidence_logs)
        """
        role_rule = self.rule_engine.get_role_rule(job_role)
        weighted_categories = role_rule.get("weighted", [])

        score_breakdown: Dict[str, float] = {}
        evidence_logs: Dict[str, List[str]] = {}
        total_score = 0.0

        candidate_skills: Dict[str, Any] = {}
        skill_names: List[str] = []

        if isinstance(profile.skills, list):
            for s in profile.skills:
                if hasattr(s, "name"):
                    candidate_skills[s.name.lower()] = s
                    skill_names.append(s.name)
                elif isinstance(s, dict) and "name" in s:
                    candidate_skills[s["name"].lower()] = s
                    skill_names.append(s["name"])
                elif isinstance(s, str):
                    candidate_skills[s.lower()] = s
                    skill_names.append(s)
        
        # Gather all text elements safely into a single searchable string
        text_elements = list(skill_names)
        for ed in profile.education:
            if getattr(ed, 'degree', None): text_elements.append(ed.degree)
            if getattr(ed, 'field', None): text_elements.append(ed.field)
        for work in profile.work_experience:
            if getattr(work, 'role', None): text_elements.append(work.role)
            if getattr(work, 'company', None): text_elements.append(work.company)
            if getattr(work, 'highlights', None): text_elements.extend(work.highlights)

        combined_text = " ".join(text_elements).lower()

        # Experience depth multiplier
        exp_bonus = min(1.2, 1.0 + (profile.total_years_experience * 0.05))

        for category in weighted_categories:
            cat_name = category.get("category")
            max_weight = float(category.get("weight", 0))
            keywords = [k.lower() for k in category.get("keywords", [])]

            matched_keywords = []
            category_evidence = []

            for kw in keywords:
                if kw in candidate_skills:
                    matched_keywords.append(kw)
                    skill_obj = candidate_skills[kw]
                    snippet = getattr(skill_obj, 'evidence_snippet', None) if not isinstance(skill_obj, (str, dict)) else None
                    if snippet:
                        category_evidence.append(snippet)
                    else:
                        category_evidence.append(f"Skill '{kw}' detected in candidate profile.")
                elif kw in combined_text:
                    matched_keywords.append(kw)
                    category_evidence.append(f"Mention of '{kw}' found in resume details.")

            if keywords:
                ratio = len(matched_keywords) / len(keywords)
                # If candidate matches at least 1 keyword in category, scale score fairly
                if len(matched_keywords) > 0:
                    match_ratio = min(1.0, max(0.75, ratio * 1.5))
                else:
                    match_ratio = 0.0
            else:
                match_ratio = 1.0

            awarded_points = round(min(max_weight, max_weight * match_ratio * exp_bonus), 2)
            score_breakdown[cat_name] = awarded_points
            evidence_logs[cat_name] = category_evidence if category_evidence else [f"No direct match for keywords: {', '.join(keywords[:3])}"]
            total_score += awarded_points

        final_total_score = min(100.0, round(total_score, 2))
        return final_total_score, score_breakdown, evidence_logs
