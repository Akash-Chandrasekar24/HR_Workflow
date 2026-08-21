import os
import json
import re
import structlog
from typing import Dict, Any, List, Optional
from app.core.config import settings

logger = structlog.get_logger(__name__)


class GeminiInterviewerRecommender:
    """
    AI-Powered Technical Interviewer Recommendation Engine:
    Uses Google Gemini (LLM) with a dedicated system prompt to evaluate candidate resumes
    and match them against the technical interviewer roster, balancing technical skill alignment
    with live interviewer workloads.
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")

    def recommend(
        self,
        candidate_record: Dict[str, Any],
        interviewers_with_workload: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Evaluates candidate profile and interviewer roster to return ranked recommendations.
        Uses Gemini LLM if API key is present, with automatic fallback to heuristic match.
        """
        if not interviewers_with_workload:
            return []

        # 1. Try Gemini LLM Matching if API key is configured
        if self.api_key:
            try:
                llm_results = self._recommend_with_gemini(candidate_record, interviewers_with_workload)
                if llm_results and len(llm_results) > 0:
                    return llm_results
            except Exception as e:
                logger.warning("Gemini Interviewer Recommender failed, falling back to heuristic engine", error=str(e))

        # 2. Fallback to Deterministic Heuristic Recommender
        return self._fallback_recommend(candidate_record, interviewers_with_workload)

    def _recommend_with_gemini(
        self,
        candidate_record: Dict[str, Any],
        interviewers_with_workload: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        cand_name = candidate_record.get("candidate_name", "Applicant")
        raw_role = candidate_record.get("job_role", "AI_ENGINEER")
        job_role = raw_role.replace("_", " ").title()
        reasoning = candidate_record.get("reasoning") or candidate_record.get("decision_reason") or ""
        form_responses = candidate_record.get("form_responses", {})
        score = candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "85"

        roster_summary = []
        for emp in interviewers_with_workload:
            roster_summary.append({
                "employee_id": emp.get("employee_id"),
                "employee_name": emp.get("employee_name"),
                "department": emp.get("department"),
                "role": emp.get("role"),
                "domain": emp.get("domain"),
                "skills": emp.get("skills", []),
                "total_assigned_candidates": emp.get("total_assigned", 0),
                "meetings_fixed": emp.get("meetings_fixed", 0)
            })

        system_instruction = """
You are an expert Principal Technical Recruiter and Hiring Panel Matchmaker for GWC DATA.AI.
Your goal is to match shortlisted candidates to the best-suited technical interviewer from the employee roster.

MATCHING CRITERIA:
1. Priority 1 (Technical Skill Fit - 70%):
   - Analyze the candidate's core technologies, frameworks, and projects.
   - Match against each interviewer's specialized 'skills' list (e.g., GenAI/LLM/RAG vs Deep Learning/PyTorch vs React/TypeScript vs FastAPI/PostgreSQL vs SQL/Data Warehousing).
   - Domain alignment (AI Engineer, Full Stack, Data Analyst) is primary.

2. Priority 2 (Workload & Capacity Load Balancing - 30%):
   - Check 'total_assigned_candidates' for each interviewer.
   - If a top-skilled interviewer already has high load (e.g. 2+ candidates), recommend the next best suited available engineer with matching skills to balance team capacity.
   - Available interviewers (0 active loads) should be prioritized when skill overlap is comparable.

OUTPUT FORMAT:
Return ONLY a valid JSON object adhering strictly to this JSON schema:
{
  "top_recommendation": {
    "employee_id": "string",
    "employee_name": "string",
    "match_score": 95.0,
    "matched_skills": ["string"],
    "ai_reasoning": "string explanation"
  },
  "ranked_interviewers": [
    {
      "employee_id": "string",
      "employee_name": "string",
      "match_score": 95.0,
      "matched_skills": ["string"],
      "is_top_match": true,
      "ai_reasoning": "string explanation"
    }
  ]
}
"""

        user_prompt = f"""
Evaluate this candidate and recommend the best technical interviewer:

Candidate Details:
- Name: {cand_name}
- Applied Position: {job_role}
- Screening Score: {score}/100
- AI Screening Summary & Skills: {reasoning}
- Form Submissions: {json.dumps(form_responses)}

Active Technical Interviewer Roster:
{json.dumps(roster_summary, indent=2)}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1,
                response_mime_type="application/json"
            )
        )

        if not response.text:
            return None

        # Clean JSON text
        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        parsed = json.loads(cleaned_text.strip())
        ranked_list = parsed.get("ranked_interviewers", [])

        # Merge with original interviewer metadata
        interviewer_lookup = {emp["employee_id"]: emp for emp in interviewers_with_workload}
        final_recommendations = []

        for item in ranked_list:
            emp_id = item.get("employee_id")
            base_info = interviewer_lookup.get(emp_id, {})
            if base_info:
                final_recommendations.append({
                    **base_info,
                    "match_score": float(item.get("match_score", 50.0)),
                    "matched_skills": item.get("matched_skills", []),
                    "is_top_match": item.get("is_top_match", False),
                    "recommendation_reason": item.get("ai_reasoning", base_info.get("role", "Interviewer")),
                    "ai_reasoning": item.get("ai_reasoning", "")
                })

        # Append any unranked interviewers at bottom
        ranked_ids = {r["employee_id"] for r in final_recommendations}
        for emp in interviewers_with_workload:
            if emp["employee_id"] not in ranked_ids:
                final_recommendations.append({
                    **emp,
                    "match_score": 30.0,
                    "matched_skills": [],
                    "is_top_match": False,
                    "recommendation_reason": emp.get("role", "Interviewer"),
                    "ai_reasoning": "Alternative lead available."
                })

        if final_recommendations:
            final_recommendations[0]["is_top_match"] = True

        logger.info("Successfully generated Gemini LLM interviewer recommendations", top=final_recommendations[0]["employee_name"] if final_recommendations else "None")
        return final_recommendations

    def _fallback_recommend(
        self,
        candidate_record: Dict[str, Any],
        interviewers_with_workload: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Deterministic heuristic matching fallback.
        """
        raw_role = candidate_record.get("job_role", "")
        reasoning = (candidate_record.get("reasoning") or candidate_record.get("decision_reason") or "").lower()
        form_responses = candidate_record.get("form_responses", {})
        form_text = " ".join([f"{k} {v}" for k, v in form_responses.items()]).lower() if isinstance(form_responses, dict) else ""
        combined_cand_text = f"{raw_role} {reasoning} {form_text}".lower()

        role_upper = raw_role.upper()
        if "AI" in role_upper or "ML" in role_upper or "LEARNING" in role_upper or "GENAI" in role_upper:
            target_domain = "AI_ENGINEER"
        elif "DATA" in role_upper or "ANALYST" in role_upper or "BI" in role_upper:
            target_domain = "DATA_ANALYST"
        else:
            target_domain = "FULLSTACK_DEV"

        recommendations = []

        for emp in interviewers_with_workload:
            emp_skills = emp.get("skills", [])
            emp_domain = emp.get("domain", "")
            total_assigned = emp.get("total_assigned", 0)

            is_same_domain = (emp_domain == target_domain)
            base_score = 50.0 if is_same_domain else 20.0

            matched_skills = []
            for skill in emp_skills:
                skill_clean = skill.lower().strip()
                if re.search(r"\b" + re.escape(skill_clean) + r"\b", combined_cand_text):
                    matched_skills.append(skill)
                elif len(skill_clean) > 3 and skill_clean in combined_cand_text:
                    matched_skills.append(skill)

            raw_skill_fit = base_score + min(48.0, len(matched_skills) * 16.0)
            workload_penalty = total_assigned * 10.0
            final_score = max(15.0, min(98.0, round(raw_skill_fit - workload_penalty, 1)))

            if is_same_domain:
                load_txt = "Available (0 active loads)" if total_assigned == 0 else f"{total_assigned} active loads"
                if matched_skills:
                    skills_str = ", ".join(matched_skills[:3])
                    reason = f"⭐ {round(raw_skill_fit)}% Skill Fit ({skills_str}) • {load_txt}"
                else:
                    reason = f"{emp.get('role')} • {load_txt}"
            else:
                reason = f"Alternative Domain • {total_assigned} active loads"

            recommendations.append({
                **emp,
                "skills": emp_skills,
                "total_assigned": total_assigned,
                "skill_fit_score": round(raw_skill_fit, 1),
                "match_score": final_score,
                "matched_skills": matched_skills,
                "is_same_domain": is_same_domain,
                "recommendation_reason": reason,
                "ai_reasoning": reason,
                "is_top_match": False
            })

        recommendations.sort(key=lambda x: (x["is_same_domain"], x["match_score"], -x["total_assigned"]), reverse=True)

        if recommendations:
            recommendations[0]["is_top_match"] = True
            top_name = recommendations[0]["employee_name"]
            top_skills = ", ".join(recommendations[0]["matched_skills"][:2]) if recommendations[0]["matched_skills"] else recommendations[0]["role"]
            top_load = recommendations[0]["total_assigned"]
            load_tag = f"{top_load} active" if top_load > 0 else "Fully Available"
            recommendations[0]["recommendation_reason"] = f"⭐ AI Top Recommendation ({recommendations[0]['match_score']}% Match | {load_tag}): {top_name} specializes in {top_skills}."
            recommendations[0]["ai_reasoning"] = recommendations[0]["recommendation_reason"]

        return recommendations


gemini_recommender = GeminiInterviewerRecommender()
