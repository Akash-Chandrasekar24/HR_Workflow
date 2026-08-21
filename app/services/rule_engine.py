import json
import structlog
from pathlib import Path
from typing import Dict, Any, Tuple, List
from app.core.config import settings
from app.schemas.candidate import StructuredCandidateProfile

logger = structlog.get_logger(__name__)


class RuleEngineService:
    """
    Evaluates Candidate Profile against Role-Specific HR Mandatory Rules.
    Determines mandatory pass/fail status and returns detailed failure reasons.
    """

    def __init__(self, rules_path: str = None):
        self.rules_path = rules_path or settings.rules_absolute_path
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        """Loads job rules JSON configuration file."""
        path = Path(self.rules_path)
        if not path.exists():
            logger.warning("Rules file not found. Using default empty rules dict.", path=str(path))
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load rules JSON configuration", error=str(e))
            return {}

    @property
    def rules_config(self) -> Dict[str, Any]:
        """Property alias for API routers."""
        return self.rules

    def normalize_role_code(self, raw_role: str) -> str:
        """Normalizes user role input strings & handles common typos to strictly 3 roles: AI_ENGINEER, FULLSTACK_DEV, DATA_ANALYST."""
        if not raw_role:
            return "AI_ENGINEER"
        
        role_clean = raw_role.strip().upper().replace(" ", "_")
        
        # Check direct match first
        if role_clean in self.rules:
            return role_clean
            
        # Fuzzy match patterns
        if "AI" in role_clean or "ML" in role_clean or "ENGINNER" in role_clean or "LEARNING" in role_clean or "GENAI" in role_clean:
            return "AI_ENGINEER"
        if "DATA" in role_clean or "ANALYST" in role_clean or "BI" in role_clean or "ANALYTICS" in role_clean:
            return "DATA_ANALYST"
        if "FULL" in role_clean or "STACK" in role_clean or "PYTHON" in role_clean or "BACKEND" in role_clean or "WEB" in role_clean or "DEV" in role_clean:
            return "FULLSTACK_DEV"

        return "FULLSTACK_DEV"


    def get_role_rule(self, role_code: str) -> Dict[str, Any]:
        """Retrieves rule configuration for a normalized job role."""
        normalized = self.normalize_role_code(role_code)
        rule = self.rules.get(normalized)
        if not rule:
            logger.warning("Job role rule not found. Falling back to PYTHON_DEV", requested_role=role_code)
            return self.rules.get("PYTHON_DEV", {})
        return rule

    def evaluate_mandatory(self, profile: StructuredCandidateProfile, role_code: str) -> Tuple[bool, List[str], List[str]]:
        """
        Evaluates mandatory Boolean pass/fail criteria from role rule configuration.
        Returns: (mandatory_passed: bool, passed_checks: List[str], failure_reasons: List[str])
        """
        role_rule = self.get_role_rule(role_code)
        mandatory_list = role_rule.get("mandatory", [])
        
        passed_checks = []
        failure_reasons = []

        # Extract candidate skill names safely
        cand_skills = []
        if isinstance(profile.skills, list):
            for s in profile.skills:
                if hasattr(s, "name"):
                    cand_skills.append(s.name.lower())
                elif isinstance(s, dict) and "name" in s:
                    cand_skills.append(s["name"].lower())
                elif isinstance(s, str):
                    cand_skills.append(s.lower())
        elif hasattr(profile.skills, 'technical_skills'):
            cand_skills = [str(s).lower() for s in getattr(profile.skills, 'technical_skills', [])] + \
                          [str(s).lower() for s in getattr(profile.skills, 'frameworks', [])]

        cand_skills_blob = " ".join(cand_skills)

        for rule_item in mandatory_list:
            field = rule_item.get("field")
            rule_type = rule_item.get("type")
            target_val = rule_item.get("value")
            label = rule_item.get("label", f"{field} check")

            if rule_type == "min_value" and field == "total_years_experience":
                min_years = float(target_val)
                actual_years = profile.total_years_experience
                if actual_years >= min_years:
                    passed_checks.append(f"PASS: {label} ({actual_years} yrs >= {min_years} yrs)")
                else:
                    failure_reasons.append(f"FAIL: {label} (Required {min_years} years, candidate has {actual_years} years)")

            elif rule_type == "skill_present" and field == "skills":
                req_skill = str(target_val).lower()
                if req_skill in cand_skills_blob:
                    passed_checks.append(f"PASS: {label}")
                else:
                    failure_reasons.append(f"FAIL: Skill '{target_val}' not found in candidate profile")

            elif rule_type == "degree_present" and field == "education":
                req_deg = str(target_val).lower()
                cand_degs = " ".join([e.degree.lower() for e in profile.education if getattr(e, 'degree', None)])
                if req_deg in cand_degs or req_deg == "any":
                    passed_checks.append(f"PASS: {label}")
                else:
                    failure_reasons.append(f"FAIL: Required Degree '{target_val}' not found in candidate profile")

        mandatory_passed = len(failure_reasons) == 0
        return mandatory_passed, passed_checks, failure_reasons

    def get_all_role_jds(self) -> Dict[str, Any]:
        """Returns all role configurations with their Job Descriptions and ATS keywords."""
        self.rules = self._load_rules()
        return self.rules

    def update_role_jd(self, role_code: str, jd_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates Job Description, responsibilities, and ATS keywords for a specific role.
        Persists changes to job_rules.json.
        """
        norm_role = self.normalize_role_code(role_code)
        self.rules = self._load_rules()
        
        if norm_role not in self.rules:
            self.rules[norm_role] = {}

        # Update JD fields
        if "job_description" in jd_data:
            self.rules[norm_role]["job_description"] = jd_data["job_description"]
        if "core_responsibilities" in jd_data:
            self.rules[norm_role]["core_responsibilities"] = jd_data["core_responsibilities"]
        if "ats_keywords" in jd_data:
            self.rules[norm_role]["ats_keywords"] = jd_data["ats_keywords"]
        if "title" in jd_data:
            self.rules[norm_role]["title"] = jd_data["title"]
        if "thresholds" in jd_data:
            self.rules[norm_role]["thresholds"] = jd_data["thresholds"]

        # Persist to disk
        try:
            with open(self.rules_path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2)
            logger.info("Successfully updated Job Description and ATS keywords", role=norm_role)
        except Exception as e:
            logger.error("Failed to save updated job_rules.json", error=str(e))
            raise

        return self.rules[norm_role]

    # Alias for method compatibility
    evaluate_mandatory_criteria = evaluate_mandatory


# Alias for backward compatibility
RuleEngine = RuleEngineService
