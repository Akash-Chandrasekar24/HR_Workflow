import re
import structlog
from typing import Dict, Any, List, Optional, Set
from app.schemas.candidate import StructuredCandidateProfile
from app.services.rule_engine import RuleEngine

logger = structlog.get_logger(__name__)


class ATSEngine:
    """
    Job Description (JD) Based Keyword Matching and ATS Resume Scoring Engine.
    Evaluates candidate resumes directly against the Job Description and required technical skills.
    Gives heavy weightage to JD keywords, core responsibilities, and experience relevance without degree bias.
    """

    def __init__(self, rule_engine: Optional[RuleEngine] = None):
        self.rule_engine = rule_engine or RuleEngine()

    def _normalize_text(self, text: str) -> str:
        """Lowercases and cleans text for robust keyword matching."""
        if not text:
            return ""
        return re.sub(r"[^\w\s\+\#\.\/]", " ", text.lower())

    def _extract_candidate_text_corpus(
        self,
        profile: StructuredCandidateProfile,
        raw_resume_text: Optional[str] = None
    ) -> Set[str]:
        """
        Extracts all tokens, phrases, skill names, and experience highlights from the candidate profile.
        """
        text_corpus = set()

        # 1. Candidate Skills
        if isinstance(profile.skills, list):
            for s in profile.skills:
                if hasattr(s, "name") and s.name:
                    text_corpus.add(s.name.lower().strip())
                elif isinstance(s, dict) and "name" in s:
                    text_corpus.add(s["name"].lower().strip())
                elif isinstance(s, str):
                    text_corpus.add(s.lower().strip())

        # 2. Work Experience highlights & roles
        for work in getattr(profile, "work_experience", []):
            if getattr(work, "role", None):
                text_corpus.add(work.role.lower().strip())
            if getattr(work, "company", None):
                text_corpus.add(work.company.lower().strip())
            for hl in getattr(work, "highlights", []):
                text_corpus.add(hl.lower().strip())

        # 3. Projects & Certifications
        for proj in getattr(profile, "projects", []):
            text_corpus.add(str(proj).lower().strip())
        for cert in getattr(profile, "certifications", []):
            text_corpus.add(str(cert).lower().strip())

        # 4. Raw resume text if available
        if raw_resume_text:
            text_corpus.add(raw_resume_text.lower())

        return text_corpus

    def _keyword_present_in_corpus(self, keyword: str, corpus: Set[str], full_text: str) -> bool:
        """Checks if a keyword or tech skill is present in candidate profile or raw text."""
        kw_norm = keyword.lower().strip()
        if not kw_norm:
            return False

        # Direct set lookup
        if kw_norm in corpus:
            return True

        # Regex word boundary search in combined text
        pattern = r"\b" + re.escape(kw_norm) + r"\b"
        if re.search(pattern, full_text, re.IGNORECASE):
            return True

        # Substring check in individual corpus items
        for item in corpus:
            if kw_norm in item:
                return True

        return False

    def compute_ats_score(
        self,
        profile: StructuredCandidateProfile,
        job_role: str,
        raw_resume_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Computes ATS Score (0.0–100.0%) and performs deep Keyword Match Analysis against the Job Description.
        Weights:
          - JD Keywords & Technical Skills Match: 60% (Mandatory: 35%, Preferred: 25%)
          - JD Core Responsibilities Alignment: 25%
          - Experience Relevance: 15%
        """
        role_rule = self.rule_engine.get_role_rule(job_role)
        role_title = role_rule.get("title", job_role.replace("_", " ").title())
        ats_config = role_rule.get("ats_keywords", {})
        responsibilities = role_rule.get("core_responsibilities", [])

        mandatory_kws = ats_config.get("mandatory_keywords", [])
        preferred_kws = ats_config.get("preferred_keywords", [])
        good_to_have_kws = ats_config.get("good_to_have_keywords", [])

        corpus = self._extract_candidate_text_corpus(profile, raw_resume_text)
        full_text = " ".join(corpus)

        # 1. Match Mandatory Keywords (35 pts max)
        matched_mandatory = []
        missing_mandatory = []
        for kw in mandatory_kws:
            if self._keyword_present_in_corpus(kw, corpus, full_text):
                matched_mandatory.append(kw)
            else:
                missing_mandatory.append(kw)

        mand_ratio = len(matched_mandatory) / len(mandatory_kws) if mandatory_kws else 1.0
        score_mandatory_kws = round(mand_ratio * 35.0, 2)

        # 2. Match Preferred Keywords (30 pts max)
        matched_preferred = []
        missing_preferred = []
        for kw in preferred_kws:
            if self._keyword_present_in_corpus(kw, corpus, full_text):
                matched_preferred.append(kw)
            else:
                missing_preferred.append(kw)

        # In real-world screening, matching 3-4 specialized tools demonstrates high preferred skill mastery
        target_pref_benchmark = min(len(preferred_kws), 4) if preferred_kws else 1
        pref_ratio = min(1.0, len(matched_preferred) / max(1, target_pref_benchmark))
        score_preferred_kws = round(pref_ratio * 30.0, 2)

        # 3. Match Good to Have Keywords (Bonus buffer, up to 5 pts)
        matched_good_to_have = []
        for kw in good_to_have_kws:
            if self._keyword_present_in_corpus(kw, corpus, full_text):
                matched_good_to_have.append(kw)
        bonus_pts = round(min(5.0, len(matched_good_to_have) * 1.5), 2)

        # Combined Keyword Match Metric
        all_target_kws = list(dict.fromkeys(mandatory_kws + preferred_kws))
        all_matched_kws = list(dict.fromkeys(matched_mandatory + matched_preferred + matched_good_to_have))
        all_missing_kws = list(dict.fromkeys(missing_mandatory + missing_preferred))

        keyword_match_pct = round((len(all_matched_kws) / max(1, len(all_target_kws))) * 100.0, 1)
        keyword_match_pct = min(100.0, keyword_match_pct)

        # 4. JD Core Responsibilities Alignment (20 pts max)
        resp_matches = 0
        for resp in responsibilities:
            resp_words = [w for w in re.findall(r"\w+", resp.lower()) if len(w) > 3]
            hit_count = sum(1 for w in resp_words if w in full_text)
            if resp_words and (hit_count / len(resp_words)) >= 0.20:
                resp_matches += 1

        resp_ratio = (resp_matches / len(responsibilities)) if responsibilities else 1.0
        score_responsibilities = round(min(20.0, max(8.0, resp_ratio * 20.0)), 2)

        # 5. Experience Relevance (15 pts max)
        exp_years = float(getattr(profile, "total_years_experience", 0.0))
        if exp_years >= 2.5:
            score_experience = 15.0
        elif exp_years >= 1.0:
            score_experience = 13.0
        elif exp_years >= 0.5:
            score_experience = 11.0
        else:
            # Entry level with projects
            score_experience = 10.0 if len(getattr(profile, "projects", [])) > 0 else 8.0

        # Calculate Total ATS Score (0 - 100)
        total_ats_score = round(min(100.0, score_mandatory_kws + score_preferred_kws + bonus_pts + score_responsibilities + score_experience), 1)

        # Determine ATS Verdict
        if total_ats_score >= 80.0:
            verdict = "STRONG_MATCH"
            verdict_label = "High ATS Match"
        elif total_ats_score >= 60.0:
            verdict = "GOOD_MATCH"
            verdict_label = "Moderate ATS Match"
        else:
            verdict = "LOW_MATCH"
            verdict_label = "Low ATS Match"

        # Summary Prose
        matched_str = ", ".join(all_matched_kws[:6]) if all_matched_kws else "None"
        missing_str = ", ".join(all_missing_kws[:4]) if all_missing_kws else "None"

        ats_summary = (
            f"ATS Score: {total_ats_score}% ({verdict_label}). "
            f"Matched {len(all_matched_kws)}/{len(all_target_kws)} target JD keywords ({matched_str}). "
            f"Key missing skills: {missing_str}."
        )

        logger.info(
            "Computed ATS score for candidate",
            role=job_role,
            ats_score=total_ats_score,
            matched_kws=len(all_matched_kws),
            missing_kws=len(all_missing_kws)
        )

        return {
            "ats_score": total_ats_score,
            "keyword_match_percentage": keyword_match_pct,
            "matched_keywords": all_matched_kws,
            "missing_keywords": all_missing_kws,
            "matched_mandatory": matched_mandatory,
            "missing_mandatory": missing_mandatory,
            "matched_count": len(all_matched_kws),
            "target_keywords_count": len(all_target_kws),
            "ats_breakdown": {
                "jd_mandatory_keywords": score_mandatory_kws,
                "jd_preferred_keywords": score_preferred_kws,
                "jd_responsibilities_alignment": score_responsibilities,
                "experience_relevance": score_experience
            },
            "ats_verdict": verdict,
            "ats_verdict_label": verdict_label,
            "ats_summary": ats_summary,
            "job_role_title": role_title
        }


ats_engine = ATSEngine()
