import os
import json
import structlog
from typing import Dict, Any, Optional
from app.core.config import settings

logger = structlog.get_logger(__name__)


class GeminiHITLService:
    """
    Human-in-the-Loop (HITL) AI Re-Evaluation Service:
    Empowers HR Recruiters to guide, refine, and re-evaluate AI candidate screening decisions
    using natural language feedback and directives.
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY")

    def re_evaluate_candidate(
        self,
        candidate_record: Dict[str, Any],
        hr_feedback: str,
        raw_resume_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Re-evaluates a candidate based on custom HR recruiter feedback and guidance.
        Uses Google Gemini (LLM) if available, with robust fallback.
        """
        if not hr_feedback or not hr_feedback.strip():
            return {
                "revised_score": float(candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or 80.0),
                "revised_decision": candidate_record.get("status", "SHORTLISTED"),
                "revised_reasoning": candidate_record.get("reasoning", ""),
                "hr_feedback_applied_summary": "No feedback provided; retained original assessment.",
                "suggested_action": "APPROVE"
            }

        # 1. Try Gemini LLM Re-Evaluation
        if self.api_key:
            try:
                llm_result = self._re_evaluate_with_gemini(candidate_record, hr_feedback, raw_resume_text)
                if llm_result:
                    return llm_result
            except Exception as e:
                logger.warning("Gemini HITL re-evaluation failed, falling back to heuristic engine", error=str(e))

        # 2. Heuristic Fallback
        return self._fallback_re_evaluate(candidate_record, hr_feedback)

    def _re_evaluate_with_gemini(
        self,
        candidate_record: Dict[str, Any],
        hr_feedback: str,
        raw_resume_text: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        cand_name = candidate_record.get("candidate_name", "Applicant")
        raw_role = candidate_record.get("job_role", "AI_ENGINEER")
        job_role = raw_role.replace("_", " ").title()
        prev_score = candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or "80"
        prev_reason = candidate_record.get("reasoning") or candidate_record.get("decision_reason") or ""
        context_text = raw_resume_text or prev_reason

        system_instruction = """
You are an expert Principal Technical Recruiter and Human-in-the-Loop AI Assistant for GWC DATA.AI.
The HR Recruiter has reviewed a candidate and provided specific feedback, critique, or criteria adjustments.
Your task is to re-evaluate the candidate's profile and qualifications, directly incorporating the HR Recruiter's instructions.

DIRECTIVES:
1. Re-examine the candidate's technical profile in light of the HR's feedback (e.g., giving more weight to certain skills, reconsidering experience, or adjusting thresholds).
2. Produce a revised score (0.0 to 100.0) reflecting the HR's guidance.
3. Write a revised natural-language reasoning statement that explicitly acknowledges and incorporates the HR's guidance.
4. Recommend a clear suggested action: "APPROVE", "HOLD", or "REJECT".

OUTPUT FORMAT:
Return ONLY a valid JSON object matching this schema:
{
  "revised_score": 92.0,
  "revised_decision": "SHORTLISTED",
  "revised_reasoning": "Re-evaluated per HR guidance: ...",
  "hr_feedback_applied_summary": "Brief 1-sentence summary of how HR feedback was applied",
  "suggested_action": "APPROVE"
}
"""

        user_prompt = f"""
Candidate Details:
- Name: {cand_name}
- Applied Role: {job_role}
- Previous Screening Score: {prev_score}/100
- Previous AI Reasoning: {prev_reason}
- Resume Context & Skills: {context_text[:2000]}

HR Recruiter Feedback & Instructions:
"{hr_feedback}"

Please re-evaluate the candidate and return the updated assessment JSON.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                response_mime_type="application/json"
            )
        )

        if not response.text:
            return None

        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]

        parsed = json.loads(cleaned_text.strip())
        logger.info("Successfully executed Gemini HITL re-evaluation", candidate=cand_name, revised_score=parsed.get("revised_score"))
        return {
            "revised_score": float(parsed.get("revised_score", prev_score)),
            "revised_decision": parsed.get("revised_decision", "SHORTLISTED"),
            "revised_reasoning": parsed.get("revised_reasoning", prev_reason),
            "hr_feedback_applied_summary": parsed.get("hr_feedback_applied_summary", "Updated per HR feedback."),
            "suggested_action": parsed.get("suggested_action", "APPROVE")
        }

    def _fallback_re_evaluate(
        self,
        candidate_record: Dict[str, Any],
        hr_feedback: str
    ) -> Dict[str, Any]:
        """
        Deterministic fallback for re-evaluation when offline.
        """
        try:
            curr_score = float(candidate_record.get("weightage_score") or candidate_record.get("weighted_score") or 80.0)
        except (ValueError, TypeError):
            curr_score = 80.0

        fb_lower = hr_feedback.lower()
        score_adj = 0.0

        if any(w in fb_lower for w in ["increase", "boost", "higher", "approve", "strong", "promote", "excellent"]):
            score_adj = +8.0
        elif any(w in fb_lower for w in ["decrease", "lower", "reduce", "weak", "penalty", "reject", "doubt"]):
            score_adj = -10.0

        revised_score = max(10.0, min(99.0, round(curr_score + score_adj, 1)))
        cand_name = candidate_record.get("candidate_name", "Applicant")
        role = candidate_record.get("job_role", "Role").replace("_", " ").title()

        revised_reason = (
            f"Re-evaluated per HR guidance: Candidate '{cand_name}' was reassessed for {role}. "
            f"HR note applied: \"{hr_feedback}\". Score updated to {revised_score}/100."
        )

        return {
            "revised_score": revised_score,
            "revised_decision": "SHORTLISTED" if revised_score >= 60 else "REJECTED",
            "revised_reasoning": revised_reason,
            "hr_feedback_applied_summary": f"Applied HR guidance: {hr_feedback[:60]}...",
            "suggested_action": "APPROVE" if revised_score >= 60 else "REJECT"
        }


hitl_service = GeminiHITLService()
